# 118 — A criterion that the recorded prices agree with the recorded `pair_decimals`

**Owner:** C — Interface and models

**Phase:** 6. Operator ruling 2026-09-18, from spec 101's mark measurement. Scheduled **after the
nine criteria are green**, alongside the seed-vocabulary work.

## Goal

A phase 6 criterion asserting that, for every pair carried by **both**
`tests/fixtures/book_sample.jsonl` and `tests/fixtures/kraken/asset_pairs.json`, the recorded book
prices agree with that pair's recorded `pair_decimals` declaration.

## Why it is worth having, and what it is not

**It is not a check on Kraken.** Both sides are recordings frozen together, so it can never go red
because the exchange changed its own settings — that would be news, and a check that fires on
someone else's decision is a check that gets ignored. It can only go red if a **re-cut fixture is
internally inconsistent**: a new book sample landing beside a stale `AssetPairs` entry. Every other
criterion that reads those fixtures rests on their agreement, and today nothing would notice.

## Implementation

1. Build-log entry first.
2. The criterion reads **those two committed fixtures and nothing else** — no `data/raw/`, no
   network — and passes on a fresh clone like every other criterion.
3. **A pair in one fixture and absent from the other is reported by name, never skipped
   silently.** ADA/USD is the case that motivates this: the recorded `AssetPairs` has no entry for
   it, so there was no declaration to compare against. A criterion quietly covering fewer pairs
   than it appears to is weaker than one that says so.
4. **The message states how many pairs were compared and how many could not be**, so a reader takes
   the coverage from the message rather than inferring it from a PASS.
5. **Prove it can fail:** in a copied tree, edit a fixture so a price carries more decimals than its
   declaration; observe the FAIL naming the pair and the figure; restore and compare the sha256 in
   the same statement. Plus an equivalent control whose line text you grep for first.
6. **Keep the spec 101 measurement as prose beside the criterion** — dated, and naming the archive
   the fixture was cut from. It explains why the check exists, and a dated observation about one
   recording is honest as long as it says which recording.

## Scope Limits

- `scripts/verify.py`, `tests/verify/**` and your records only. Do not edit the fixtures
  themselves, any engine, or A's cutter.
- Do not assert anything about pairs the fixtures do not both carry, and do not infer a precision
  from prices.

## Check When Done

- PENDING, PASS and FAIL all observed, the FAIL from the fixture mutation above.
- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
