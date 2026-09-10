# Build log — Phase 3 — lead

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem
and its fix, and every decision where two approaches were viable. Not at the end of
the session — three IDE crashes in Phase 1 each took the code and the log at different
moments, and only the entries already written survived.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-3.md` at phase close.

## Entries

### A config key and its model field cannot land separately

**Agent:** Lead · **Task:** spec 37 · **Date:** 2026-09-10

**What happened.** Spec 37 called for two new keys under `kraken:` in
`config/default.yaml`. I added them, and `load_config()` raised:

```
kraken.cache_ttl_s
  Extra inputs are not permitted [type=extra_forbidden, input_value={'asset_pairs': 300, 'trade_volume': 60}, input_type=dict]
```

Every test in the tree fails on that, because almost everything loads the committed
config. I reverted inside the same minute.

**Why.** `KrakenConfig` in `platform/config.py` is a `_Section`, and every section sets
`extra="forbid"` — deliberately, so that a typo in a key name is a startup refusal
rather than a silently ignored setting. That makes the YAML and the model field two
halves of one change. And they have different owners: the lead authors
`config/default.yaml`, Agent A owns the loader. `ownership.md` already says "A may
request a config key; only the lead adds one", which describes the request direction
but not the landing order.

**Fix.** Ordered the halves rather than the ownership. Spec 38's step 1 became "add the
field to `KrakenConfig`, then tell the lead", and spec 37 grew an appendix carrying the
YAML block verbatim so the lead's half is a single paste that cannot drift from what A
validated against. A landed the field, published a handoff note in
`context/progress/a-platform.md`, and I pasted the block and confirmed both keys resolve
through `Config.get` before touching anything else.

**Consequence.** A made one call I want to record as A's rather than mine, because it is
the non-obvious half: the field is `CacheTtlConfig | None = None`, not required. A
required field would have made the *shipped* config raise until the YAML caught up —
the same failure I hit, with the halves reversed — and spec 38 explicitly told A to test
against a fabricated config until the YAML landed, which is only possible if the
committed file still loads. `None` is not a fallback: `Config.get` raises when asked to
descend through it and the REST client raises rather than caching for a guessed
interval, so an absent TTL fails closed at the point of use. Now that the YAML is in,
the field is tightened to required so a later removal refuses at startup instead.

**A generalisation worth carrying.** Any change that spans an ownership boundary in a
file pair where one half validates the other has a landing order, and the order is not
implied by who owns what. `ownership.md`'s seam table names producers and consumers; it
does not name which half may exist alone. This is the second seam this project has found
that way — the first was the command reader, where both halves passed their own tests
while disagreeing with each other.

### The IDE crashed with three agents mid-flight, and the log was the thing that was lost

**Agent:** Lead · **Task:** phase 3 wave 1 · **Date:** 2026-09-10

**What happened.** The IDE crashed while A, B and C were all working. On restart the
session had no completion record for any of them. The IDE had also committed the
working tree as `7c4f012` — a commit no agent made and no agent was authorised to make.

The tree was left genuinely red, and specifically: B had removed `EXCHANGE_FEES_KEY` and
`EXCHANGE_FALLBACKS_KEY` from `engines/cost/contracts.py` while `engine.py` still
referenced them, so `mypy --strict` reported six name-errors and 25 tests failed. That
is a deterministic failure and worth distinguishing loudly from this machine's known
intermittent fault, because the standing instruction on a FAIL is to re-run the named
test in isolation — advice that would have wasted time here.

**Why.** Nothing to diagnose in the crash itself; it is the known limitation recorded
under Known Risks. What is worth recording is the state it left: source code half-edited
and committed, progress files intact, **and all four `docs/build-log/phase-3/*.md` still
empty stubs.**

**Fix.** Assessed the tree before resuming anything — `git show --stat` on the unexpected
commit, `load_config()`, then the full gate — rather than restarting the agents blind.
Completed the lead half of the config handoff, which A's surviving progress note had
unblocked. Then resumed all three from their saved transcripts, each with a written
account of what had changed underneath them: what survived, what did not, that the red
tree was B's and not theirs, and that the config now differs from when they started.

**Consequence.** The code survived and the reasoning did not. Progress files survived
because agents write them before starting work; build logs did not, because the natural
moment to write one feels like the end of a task. That is exactly backwards, and
`script-rules.md` rule 1 already says so — "write the entry when you fix the thing, not
at the end of the session". Phase 1 lost work to three IDE crashes and produced that
rule; this is the first time the rule has been tested against a crash with several
agents running, and the rule held for the file it covers while the gap it leaves is that
nothing enforces it mid-task. Each resumed agent was told to write down anything it
still remembered from before the crash while it still had it. Whatever was not
remembered is gone, and it is gone in the way this project has already decided is
worst: a bug that was fixed and not recorded is a bug that never happened.

