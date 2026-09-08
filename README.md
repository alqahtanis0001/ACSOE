# ACSOE — Adaptive Crypto Spot Opportunity Engine

An automated spot trading system for Kraken, built as a Master's dissertation project.

Its philosophy is **reject first; execute only with verified net edge**. Twenty-three engines run in a fixed order, and most of them exist to say no. Nine contain no machine learning at all — the components that protect capital are auditable arithmetic, not models anyone has to trust.

## What it does

1. Streams and records market data for every Kraken pair.
2. Builds 15-minute candles and verifies them, or freezes.
3. Filters the tradable universe from live pair rules, live fees, and current balance.
4. Picks one candidate and puts it through four gates: is the market tradable, how far will it move, does it beat the fees, why should we say no.
5. Enters with a post-only limit order, or abandons the candidate.
6. Watches the position every minute until target, stop, or timeout.
7. Logs the outcome — and every rejection, with its reason.

It does not predict price. It predicts which of three barriers price touches first: a profit target, a stop, or a timeout.

## Status

Phase 0 of 9. See `context/progress-tracker.md`.

Live trading is disabled by default and requires three independent switches. The system runs in paper mode until a model has been trained and validated.

## Repository layout

```
AGENTS.md            entry point for coding agents — read this first
context/             the specification: invariants, contracts, standards, workflow
feature-specs/       numbered implementation units
docs/build-log/      what broke and how it was fixed, per phase
src/acsoe/           the system: core/, platform/, clients/, engines/, research/, console/, cli/
tests/               harness, fixtures, and per-agent test files
scripts/             verify.py (executable phase gates), record.py (day-one recorder)
db/migrations/       SQLite schema
config/              default.yaml, paper mode
data/                recordings, candles, database — gitignored
models/              trained artefacts — gitignored
logs/                structlog JSON output — gitignored
```

## Setup

Requires Python 3.11 or later.

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

Fill in `.env` with a **read-only** Kraken key. A trade-permission key is not needed and should not be used until Phase 8.

## Running

```
acsoe engine          # the trading daemon
acsoe console         # the local console, default http://127.0.0.1:8765
python scripts/record.py    # standalone market recorder
```

The daemon and the console are separate processes. The daemon holds the exchange connection and runs continuously; the console reads state from SQLite and writes at most three commands. **The console holds no credentials and cannot place an order.**

## Verification

```
pytest tests/ -q
mypy --strict src/
ruff check src/
python scripts/verify.py --phase N
```

Phase exit criteria are executable, not a checklist. A phase is finished when its verify run passes every criterion.

## For coding agents

Read `AGENTS.md`, then `context/` in the order it lists. `context/run-protocol.md` defines what happens when the operator says "start phase N".

## Disclaimer

Research software for a dissertation. It can lose money. Nothing here is financial advice, and it is not intended to manage anyone else's funds.
