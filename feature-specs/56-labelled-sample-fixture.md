# 56 — `tests/fixtures/labelled_sample.parquet`

**Owner:** C — Interface and models

**Phase:** 4. C deposits the evidence for C criteria, per `tests/fixtures/README.md`.

## Goal

The committed artefact the Phase 4 gate judges: a labelled slice produced by replaying a real
archive through the real loader, the real replay and the real labeller.

## Implementation

1. Produce it by **running the pipeline**, never by hand. Spec 54 gives the archive and the
   replay, spec 52 gives the labels.
2. Keep it small — evidence, not a dataset. All three outcomes must occur, and at least one
   ambiguous bar and one window containing a gap must be present, because the criterion
   asserts on them.
3. Carry provenance **in the file**: which archive, which span, which barrier settings, the
   count of ambiguous labels, and the statement that the source carries no spread and no book.
   A parquet that cannot say where it came from is indistinguishable from one written by hand,
   and the criterion is written to notice.
4. Update the table in `tests/fixtures/README.md` if anything about the deposit changed.
5. `.gitattributes` already marks `tests/fixtures/**` as `-text`; `.gitignore` already
   re-admits `*.parquet` there. Both are load-bearing and
   `tests/harness/test_fixture_tracking.py` asserts them. Confirm the committed bytes survive
   a round trip — a CRLF conversion on a parquet payload corrupts it, and an unexplained CRLF
   conversion is an open item from Phase 3.

## Rules this spec is held to

- **Never generate one by hand to make a criterion pass.** The value of the artefact is that a
  real run produced it.
- Redact nothing into it that is not market data. No key, no balance, no account activity.

## Scope Limits

- Do **not** commit the archive itself. `data/` is gitignored and a criterion may never depend
  on it.
- Do **not** grow it into a training set. Phase 5 builds its own.

## Check When Done

- `labelled_sample_replayed_from_archive` is PASS on a clean checkout.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
