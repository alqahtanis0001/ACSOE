# 86 — The paper broker wired into `acsoe engine`, and the book-fixture cutter

**Owner:** A — Platform

**Phase:** 6. `cli/` and `scripts/` (except `verify.py`) are A's.

## Goal

Two small pieces in A's lane that other agents' work depends on: in paper mode the daemon's
`clients.kraken` is B's paper broker wrapping the real client, and a script cuts a committed book
fixture out of the live archive for C to deposit.

## Implementation

1. Per the operator's ruling of 2026-09-16 (spec 88), the simulator is a client-layer paper
   broker: `cli/engine.py::build_clients` wraps `KrakenClient` in B's broker when
   `config.mode` is `paper`, and never in `live`. A test through `build_clients` itself (not a
   hand-built `Clients`) asserts which object each mode receives — the tripwire must reach the
   wiring through the code path the wiring lives on.
2. `scripts/cut_book_fixture.py`: reads `data/raw/` read-only and writes a JSONL of `book`
   snapshot and update frames for named pairs over a named UTC window, byte-for-byte as recorded,
   plus a header line naming source files, window, pairs and line counts. Invariant 11: it never
   writes into `data/raw/`. Written with an empty `newline` or bytes, because the output lands in
   `tests/fixtures/`, which is `-text`.
3. Refuses a window with a recorded `gap` marker inside it for a named pair, rather than cutting a
   fixture that silently spans a reconnect.
4. Hand the script to C, who chooses the pairs (one thin, one deep) and the window, runs it, and
   deposits the result under spec 96.

## Scope Limits

- Do **not** choose the fixture's pairs or window, or deposit it. C owns `tests/fixtures/`.
- Do **not** stop, restart or reconfigure the recorder, the recording manager or the funding
  poller. The script only reads closed and open archive files.
- Do **not** wrap the client in live mode under any flag.

## Check When Done

- The wiring test red when the paper wrap is applied in live (mutation recorded).
- The cutter run over a scratch archive with a gap inside the window refuses, naming the gap.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
