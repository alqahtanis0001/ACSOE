# 55 — Engine 23 `backtest` and the offline chain

**Owner:** A — Platform

**Phase:** 4. `cli/research.py` is A. `research/backtest.py` is assigned to A by the lead in
this phase and recorded in `context/ownership.md` in the same change — see the note at the
end of this spec.

## Goal

`acsoe research` stops being a stub. Phase 0 built it as one that reports *no offline engines
registered until Phase 4*, and this is Phase 4.

## Implementation

1. `src/acsoe/research/backtest.py` — `BacktestEngine(BaseEngine)`, `name = "backtest"`,
   `number = 23`, `is_gate = False`. In `process` it replays the archive through spec 54,
   labels it through C `research/labelling.py`, and writes the labelled slice to
   `data/derived/`. It reports counts and the span in `state["backtest"]`.
2. Register it in `OFFLINE_CHAIN` in `cli/research.py`. **Never in `bootstrap.py`** — that is
   what keeps the live loop free of `research/` imports and architecture invariant 5 true.
   Engine 20 `tournament` is Phase 7 and stays absent.
3. `acsoe research` runs the chain and prints what it produced.
4. `tests/cli/` and `tests/research/`, A lane.

## What this engine is **not**, in this phase

It does not run historical data through the twenty-three engines. Engines 5 to 16 do not
exist yet and Phase 5 and Phase 6 build them. A backtest in this phase is **replay plus
labelling**: the dataset Phase 5 trains on. Anything more is later-phase work and the phase
gate forbids it.

It also may not model a spread. The archives are OHLCVT only — no bid, no ask, no depth — so
engine 9 and the spread half of engine 10 cannot be backtested from this source, and **a
backtest that silently assumes zero spread is invalid**. Carry that statement in the output,
as `research/historical.py` already does, rather than leaving it in a docstring nobody reads
at the point of use.

## Rules this spec is held to

- **Every assertion must be proven capable of failing**, with the mutation and the red message
  recorded in `docs/build-log/phase-4/a-platform.md`. Name at least: the engine registered in
  `bootstrap.py` instead of the offline chain — the test that forbids it must be observed red
  when the import is added, or it is not guarding anything.
- `is_gate` must match the Gate column of the registry table; `is_gate_matches_registry`
  reaches engines 20 and 23 through `build_offline_chain`, which is why that function is
  importable without running the CLI.

## Scope Limits

- Do **not** add engine 20 `tournament`. Phase 7.
- Do **not** touch `bootstrap.py` or `core/`. Lead only.
- Do **not** write `research/labelling.py` or `research/walkforward.py`. They are C — call
  them, agree the signature with C directly, mock it and keep building if it is not ready.
- Do **not** train, score, promote or write to `leaderboard`.

## A note on ownership, since this path was assigned to nobody

`research/backtest.py` appears in no row of `context/ownership.md`. The lead assigns it to A
in this phase: A owns `research/replay.py` and `research/historical.py`, which is what the
engine drives, and A owns `cli/research.py`, which is where the offline chain is assembled.
C owns the labelling and walk-forward modules the engine calls, so the seam between them is
an ordinary agent seam and is recorded as one.

## Check When Done

- `acsoe research` reports a real run rather than an empty chain.
- Nothing under `acsoe.core`, `acsoe.bootstrap`, `acsoe.engines`, `acsoe.clients` imports
  `acsoe.research`, and a test asserts it.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
