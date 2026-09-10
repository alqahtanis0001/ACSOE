# 37 — The three Phase 3 rulings, into the authority documents and the config

**Owner:** Lead

**Phase:** 3 — Economics. **This spec lands first.** Every other Phase 3 spec is written
against the documents as this one leaves them, so nothing else starts until it is done.

## Goal

Three operator rulings stop being messages in a conversation and become the state of
`context/trading-invariants.md`, `context/ai-workflow-rules.md` and `config/default.yaml`,
with every contradicting sentence elsewhere corrected in the same change.

## Implementation

1. **Invariant 14 — a drawdown breach freezes, it does not liquidate.** Rewrite the
   *When it fires* section of `context/trading-invariants.md` §14 so that:
   - `close_intent` is set in exactly two ways: an operator presses Close all, or engine 17
     `safety` escalates on **a sustained data outage**. The drawdown and loss-streak limits
     are no longer escalation conditions.
   - Breaching the configured drawdown or loss-streak limit makes `safety` write a
     **`freeze`** row. Freeze stops new positions while the manage chain keeps watching the
     open ones, and the operator decides whether to liquidate. State the reasoning in one
     paragraph: a drawdown is a statement about *past* trades, and liquidating on it turns a
     paper loss into a realised one on the system's own authority, whereas a data outage is
     a statement about *present* knowledge and is the case invariant 14 was written for —
     unknown exposure is worse than a bad fill.
   - The open-position-or-resting-order precondition stays, and it now gates the outage
     escalation only.
2. **Invariant 2 — "assume tier 1" is retired.** In the paper-mode fallback table of the
   same file, replace the **Fee tier** row's fallback with *"Block that pair. No fallback."*
   and give it the reason in the same row style the other two blocking rows use:
   `AssetPairs` carries no fee schedule, so there was never a runtime source from which
   "tier 1" could be read, and a fee written into the code to stand in for it is the
   hardcoded fee `AGENTS.md` forbids. An assumed fee invalidates the cost gate exactly as an
   assumed spread does. A confirmed pair with no fee data blocks that pair.
   - **Balance is now the only paper-mode fallback in the table.** Say so in a sentence
     under it, because a table with one live row and three blocking rows reads as an
     oversight otherwise.
   - Check the sentence above the table that promises the fallbacks let "a fresh clone with
     an empty `.env` … run the pipeline and generate research data" and correct it: with an
     empty `.env` the private calls fail, so the fee tier is absent and **every pair blocks
     at the cost gate**. That is now the honest description and it must not be left claiming
     otherwise.
3. **Add the retired-term row.** In `context/ai-workflow-rules.md`'s *Retired vocabulary*
   table add `tier 1` qualified by `assume`, superseded by *"a pair with no fee data blocks;
   there is no fee fallback"*. The qualifier is required: `tier 1` is a legitimate token in
   invariant 5's reference values and in the Locked Decisions, and an unqualified row would
   make the phrase unusable across every document. Verify the matcher actually fires by
   running `python scripts/verify.py --phase 3` against a temporary reinstatement of the old
   wording before committing the new one — a retired-term row nobody has seen fail is a
   comment.
4. **Two cache TTL keys, not one.** Add to `config/default.yaml` under `kraken:`:
   `cache_ttl_s.asset_pairs: 300` and `cache_ttl_s.trade_volume: 60`, both marked
   operator-chosen 2026-09-10, with the comment saying what they are and what they are not:
   they are **our own** re-fetch interval, not a claim about anything Kraken publishes, and
   the values differ because pair rules change on the timescale of a listing while a fee
   tier changes on the timescale of a trade. `Config.get` descends through mapping values,
   so `kraken.cache_ttl_s.asset_pairs` resolves without a new section model.
5. **Do the propagation by hand, per `ai-workflow-rules.md`'s "What this check does not
   catch".** Grep `AGENTS.md`, `README.md` and every `context/*.md` for the claims these
   rulings contradict — "assume tier 1", "the worst tier", "drawdown and loss-streak limits
   are breached", and any sentence naming `safety`'s escalation conditions — and correct
   each one at its source rather than restating the new rule in a fourth file.
   `context/architecture-context.md`'s command-table section and `context/engine-contracts.md`'s
   *How the safety engine freezes the system* both name the escalation and must agree.
6. Record all three in `context/progress-tracker.md` under Decision history, and strike the
   `market_data.pairs` / `book_depth` item under Next Up with the ruling that retired it.

## Scope Limits

- Do **not** edit `src/acsoe/engines/safety/contracts.py`. The `CONDITION_ACTION` table is
  B's file and spec 42 applies the ruling there; this spec changes only the documents that
  the table implements.
- Do **not** add a `market_data.pairs` key, a `book_depth` key, or a default pair list
  anywhere. The universe is computed per tick by engine 7 — a Locked Decision.
- Do **not** add a fee, a tier threshold, or any other exchange-supplied number to
  `config/default.yaml`.
- Do **not** change `safety`'s threshold values. The operator set all five on 2026-09-08.
- Do **not** widen the retired-term row to an unqualified `tier 1`.
- Do **not** touch `bootstrap.py` here — registration is spec 47, and it lands last.

## Check When Done

- `context/trading-invariants.md` §14 names the data outage as the only `safety` escalation,
  and the drawdown and loss-streak limits as `freeze`.
- The paper-mode table's fee-tier row blocks, and no file anywhere claims a tier is assumed.
- `grep -rin "assume" AGENTS.md README.md context/ | grep -i "tier"` returns only the
  retired-vocabulary row.
- The new retired-term row was **observed to FAIL** against a reinstatement of the old
  wording, and PASSes against the new one.
- `python -c "from acsoe.platform.config import load_config; c=load_config(); print(c.get('kraken.cache_ttl_s.asset_pairs'), c.get('kraken.cache_ttl_s.trade_volume'))"` prints `300 60`.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
