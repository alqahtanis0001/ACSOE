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

### Adding a cache broke six tests that were never about caching

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** Landing the TTL cache turned seven existing tests red. Six are in
`tests/clients/kraken/test_rest.py` and one in `test_secrets.py`. The obvious reading —
the one the failure message supports — is that they all fail for the same shallow
reason: `build_client` at `test_rest.py:86` predates the constructor change, passes
neither `asset_pairs_ttl_s` nor `trade_volume_ttl_s`, and `_require_ttl` raises
`KrakenUnavailableError` naming the missing key before anything else in the call
happens. Thread the two TTLs through the helper and all seven go green.

**Why that repair would be wrong for three of them.** Those three call the *same
cached endpoint twice* against a `FixedClock` that never moves, and each of them
depends on the second call actually reaching the network:

- `test_pair_rules_come_from_the_payload_and_change_when_it_changes` alters the
  fixture between the two calls and asserts the second differs. With a TTL supplied
  and the clock standing still, the second call is a cache hit and returns the first
  snapshot. The test fails on the comparison instead — and if the comparison were
  ever weakened, it would pass while proving nothing.
- `test_the_fee_tier_comes_from_the_payload_and_changes_when_it_changes` is the same
  shape for `TradeVolume`.
- `test_pair_rules_and_balances_are_retained_across_a_later_failure` serves an error
  for the second `AssetPairs` call and asserts it raises. A cache hit returns
  successfully and nothing raises, so `pytest.raises` fails.

The three tests are testing "the value is fetched, never a constant" and "the last
known good survives a failure". Both properties are still true and both still matter;
what changed is that reaching the second fetch now requires advancing the clock past
the TTL. Making the TTL large enough to be irrelevant, or short enough that it always
expires, would have made them green while removing the interaction the cache
introduced.

**Fix.** `build_client` takes a `FixedClock` the test can move, defaults both TTLs to
distinct non-equal values, and lets a caller override either. The three tests above
advance the clock past the relevant TTL between the calls **and assert the transport
was hit again**, so a future change that made the second call a cache hit fails on the
request count rather than on a value comparison that might be relaxed.
`test_pair_rules_and_balances_are_retained_across_a_later_failure` is now the place
where spec 38's "retention survives that same expiry" is proved: the expiry is what
sends the call to the network, the network fails, the call raises, and
`last_known_good_asset_pairs` still holds the pre-expiry snapshot.
`test_the_fee_tier_and_the_book_are_deliberately_not_retained` gets the matching
negative — after the same expiry and the same failure there is no last-known-good fee
tier anywhere, because the cache is the only thing that ever held it.

**Consequence.** The cache is not a transparent optimisation. Any test that calls
`asset_pairs()` or `trade_volume()` more than once is now a test about the cache
whether it meant to be or not, and has to say which of the two it wants. That is worth
knowing before spec 39 drives two real ticks through the same client.

### A test that had gone green for the wrong reason

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** `test_a_private_call_without_credentials_blocks_rather_than_defaulting`
was **passing** through all of this, and it should not have been. It builds a client
with `credentials=None` — and, because it constructs `KrakenRestClient` directly
rather than through `build_client`, with no TTLs either — calls `trade_volume()` and
asserts `KrakenUnavailableError`. It got one. From `_require_ttl`, about
`kraken.cache_ttl_s.trade_volume`, several lines before `_private` is reached and the
credential check it exists to exercise ever runs.

**Why it matters more than the six red ones.** A red test tells you where to look. This
one was green, sitting in the middle of a file whose other tests were failing loudly,
asserting a property it had stopped testing. The exception type is the same, so
nothing in the assertion could have noticed. This is the same shape as the
`state["exchange"]` audit that the wiring specs exist for: two things agreeing on a
type while disagreeing about the subject, with a green suite over the top.

**Fix.** The test constructs with both TTLs supplied, so the TTL check passes and the
call reaches the credential check that is its actual subject. The assertion now names
the subject too — the message must mention credentials and must **not** mention
`cache_ttl_s` — so the test cannot silently start passing for a third reason later.

**Consequence.** Worth generalising: `KrakenUnavailableError` is deliberately the one
type every fail-closed path raises, which makes `pytest.raises(KrakenUnavailableError)`
on its own a weak assertion in this package. Where the *reason* is the point, the test
asserts on the message.

### Decision: no narrowing `assert` in the cache path, and therefore no suppression

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** `ruff check src/` reported two `RUF100` errors — unused `noqa`
directive, non-enabled rule `S101` — on the two `assert cached is not None` lines in
`asset_pairs()` and `trade_volume()`. `S` (flake8-bandit) is not in the selected rule
set in `pyproject.toml`, so the suppression suppressed nothing and `RUF100` is correct
to say so.

**Options.** Drop the directive and keep the bare `assert`, or remove the need for the
narrowing altogether.

**Chose.** Removed the need. `_cache_hit(cached, ttl) -> bool` became
`_fresh(cached, ttl) -> Snapshot | None`, which returns the entry when it is inside its
TTL and `None` when it is not. The call site binds the result and returns it if it is
not `None`, so the type narrows by ordinary control flow and there is nothing to assert.

**Because.** `code-standards.md` is explicit that a suppression is for a lint that
would make the code *wrong* to obey, and that one is never added to make a failing
check pass. Neither applied: the directive was inert, so obeying `RUF100` costs
nothing. That leaves the bare `assert`, and an `assert` in `src/` is a statement that
disappears under `python -O` — here it would disappear from the function that decides
whether a fee is fresh enough to price a trade. It was never load-bearing (`_cache_hit`
had already done the check) which is precisely the argument for deleting it rather than
keeping it. Making the helper return the value it has already validated is smaller than
either alternative and removes the class of problem.

**Consequence.** `_fresh` is generic over the two snapshot types through a value-
restricted `TypeVar`, so `asset_pairs()` gets a `PairRulesSnapshot | None` and
`trade_volume()` a `FeeTierSnapshot | None` rather than a union of both that would need
narrowing again at each call site.

### Decision: a construction site that cannot forget the TTLs

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** With the cache landed and the tests repaired, `grep` for
`asset_pairs_ttl_s` found it in `rest.py` and in the tests, and **nowhere else in
`src/`**. The two config keys the lead had just pasted were unreachable from the
running system: `KrakenRestClient` is constructed with two optional TTL parameters,
`clients/kraken/client.py` takes an already-built REST client, and `cli/engine.py`
still passes three `None` client slots. Wire the daemon up as it stood and every
`asset_pairs()` and `trade_volume()` call would raise about a missing TTL — with the
value sitting in `config/default.yaml` the whole time.

**Why the parameters are optional at all, since that is what allows it.** Because
tests and `scripts/` build clients directly and the absence has to fail closed at the
point of use rather than at construction — the same argument that made the config
field optional for a few hours. It is the right behaviour and it has a cost: an
optional parameter is precisely the kind of thing a caller omits by accident, and
this one had already been omitted by seven tests.

**Options.** Make the constructor require both TTLs, which turns every direct
construction into a compile-time reminder but also makes `KrakenRestClient`
unbuildable without deciding a caching policy — wrong for a script that makes one
public call. Or add a single construction path that reads config, and leave the
constructor as it is.

**Chose.** `KrakenRestClient.from_config(config, clock=..., limiter=...)`. It reads
`config.kraken.rest_timeout_s`, `config.kraken.cache_ttl_s.asset_pairs` and
`config.kraken.cache_ttl_s.trade_volume` — the two TTLs as two separate attribute
accesses on two separate fields, with no intermediate variable holding "the TTL",
because one shared value is the shape spec 38 exists to prevent and writing it down
once is how it comes back.

**The limiter is a parameter and not built here**, which is the one non-obvious part.
It is *the* limiter, shared with the WebSocket client, and a factory that made its own
would hand a single account two independent budgets against one rate limit — a bug
that shows up as a ban mid-session and not before.

**Cost.** Two ways to build the client still exist, and only one of them reads config.
`test_from_config_reads_each_ttl_from_its_own_key` asserts the config path through
behaviour rather than by reading the private fields back: it configures 1000 and 10,
parks the clock at 20 seconds, and asserts that exactly one of the two calls reached
the network. Reading the fields would only have proved that the constructor stored
what it was handed, which was never in doubt.
