# tests/fixtures

Committed evidence for `scripts/verify.py`. Small, redacted, and reproducible on a
fresh clone.

## Why these files are committed at all

Several phase criteria concern behaviour that is live, long-running, or both — a
recorder that must run for a day, a soak that must run for a week, a labelled
slice replayed from six months of archives. None of that can run inside a phase
gate, and every criterion has to pass offline on a fresh clone with no API key.

So the gate checks a **committed artefact produced by the real run**, and the real
run itself is verified by `--live`, which is opt-in and never required for a phase
to be green. A criterion that only passes on the machine that produced it is a
broken criterion.

`data/`, `models/` and `logs/` are gitignored, so nothing here may point into them.

## Who deposits what

Each agent deposits the evidence for its own criteria. Depositing a file you
produced is not writing in C's lane; C owns the *structure* of this directory and
the shared fixtures, not its contents.

| File | Agent | Criterion | Phase |
|---|---|---|---|
| `record_sample.jsonl` | A | `record_sample_valid` | 0 |
| `recording_report.json` | A | continuous 24h span with every break accounted for | 2 |
| `soak_digest.json` | A | one unbroken `run_id`, contiguous `cycle_id`s, 7 days | 8 |
| `labelled_sample.parquet` | C | labelled slice replayed from the historical CSVs | 4 |
| `kraken/*.json` | C | recorded responses backing the fake Kraken client | 0 |

`kraken/` holds `asset_pairs.json`, `balance.json`, `order_book.json` and
`trade_volume.json` — the recorded responses `tests/harness/fake_kraken.py` serves.
They are test fixtures for a fake exchange and **never** values the system falls
back on: no fee, minimum, tick size or precision in this directory is a system
default. Invariant 2 has no exceptions.

## Committability

`.gitignore` carries `*.jsonl`, `*.parquet` and `*.sqlite`, because `data/` is
large and reveals account activity. A `!tests/fixtures/**` negation re-admits
everything here. That negation is load-bearing and easy to lose, so
`tests/harness/test_fixture_tracking.py` asserts it in both directions: these paths
are not ignored, and the same extensions outside this directory still are.

`.gitattributes` marks `tests/fixtures/**` as `-text` so a Windows clone cannot
rewrite the bytes. Git's CRLF heuristic guessing wrong on a Parquet payload
corrupts it; on a JSONL sample it changes the byte count a validator reads.

## Rules

- Redact before you commit. No key, no signature, no nonce, no account balance —
  these files go into a public repository and into a dissertation.
- Keep them small. Evidence, not a dataset.
- Never generate one by hand to make a criterion pass. The artefact's whole value
  is that a real run produced it.
