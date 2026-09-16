<!-- BEGIN:kraken-agent-rules -->

# Your training data about Kraken is wrong

Kraken changed its fee tiers, minimum order sizes, and API shapes recently. Any fee percentage, tier threshold, minimum order size, or endpoint signature you remember is stale and must not be written into code.

- Fees come from `POST /0/private/TradeVolume` at runtime. Never a constant.
- Order minimums come from `GET /0/public/AssetPairs` at runtime. Never a constant.
- If a value cannot be fetched, live mode **blocks the trade**. Paper mode blocks too; its balance comes from the paper broker instead of the exchange, and there is no fallback — rule 2 of `context/trading-invariants.md`. An emergency liquidation is the one deliberate override — invariant 14 of the same file. Nothing else falls back on a default.

<!-- END:kraken-agent-rules -->

# ACSOE — Adaptive Crypto Spot Opportunity Engine

An automated spot trading system for Kraken. This is a real system that will trade real money, not a prototype.

## Read these before writing anything

In order. Do not skip.

1. `context/project-overview.md` — what this is and what is out of scope
2. `context/trading-invariants.md` — the financial rules that may never be violated
3. `context/architecture-context.md` — stack, layout, data sources, storage
4. `context/engine-contracts.md` — the engine interface and orchestrator behaviour
5. `context/ui-context.md` — console design system, tokens, layout, number rules
6. `context/code-standards.md` — Python conventions and testing
7. `context/run-protocol.md` — **what to do when the operator says "start phase N"**
8. `context/ai-workflow-rules.md` — the nine phases and their exit criteria
9. `context/ownership.md` — which agent may write which paths
10. `context/script-rules.md` — the build log you must keep as you work
11. `context/glossary.md` — domain terms
12. `context/progress-tracker.md` — where the project actually is

## Build order

Structure, then interface, then backend. Phases 0 to 8, in order, no skipping.

## Hard rules

**Phases are gates.** A phase is finished only when `python scripts/verify.py --phase N` passes every criterion. Do not begin later-phase work, even if you are blocked and it looks trivial.

**Invariants outrank tests.** If a test fails because a gate blocked a trade, the test is wrong. Never weaken, bypass, or delete a gate to make anything pass.

**Stay in your lane.** Check `context/ownership.md` before editing. Needing a path you do not own means escalating to the lead, not editing it.

**Two files get written every session.** Your own `context/progress/<agent>.md` and your own `docs/build-log/phase-N/<agent>.md`. Nothing else outside your owned paths. Only the lead writes `context/progress-tracker.md` and the consolidated `docs/build-log/phase-N.md`.

**Keep docs true.** If your implementation contradicts a context file, fix the context file in the same change.

**Never guess at trading behaviour.** A missing or ambiguous requirement is an open question in your progress file and a stop, not an invention.

**Never commit a secret.** Keys live in `.env`, which is gitignored. Never log, print, or write one anywhere.
