# 127 — A genuine `AssetPairs`, recorded and committed with its URL and date

**Owner:** A — Platform

**Phase:** 7. Closes Phase 7 prerequisite 9 together with spec 141's re-pointing.

## Goal

The repository holds a real `GET /0/public/AssetPairs` response, captured from Kraken with its URL
and UTC capture time. It is the replay client's pair rules for the simulation, and the source of a
**measured** survivorship figure for the 2023–24 window.

## Implementation

1. A script under `scripts/` fetches `AssetPairs` once through the existing client in
   `clients/kraken/`, not a second HTTP stack. It writes the response verbatim to
   `tests/fixtures/kraken/asset_pairs_recorded_<YYYY-MM-DD>.json`, with a provenance block
   carrying:
   - the URL;
   - the capture time from the injected clock;
   - the client version;
   - the sha256 of the payload as received.
2. `tests/fixtures/kraken/asset_pairs.json`, the invented Phase 0 file, **is not replaced**. The
   fake exchange and every phase criterion that reads it keep reading it. The recorded file is a
   second file with a different job.
3. **The survivorship count.** Against `data/historical/*USD_15.csv`, count the archive's USD
   pairs that trade inside the Phase 7 window but are absent from the recorded file. Name them, and
   write the count and the names to `docs/build-log/phase-7/a-platform.md`.
   `phase-7-findings.md` §7 has a slot marked NOT MEASURED for exactly this number, and the lead
   fills it from the build log.
4. **The tick-size caveat carried forward.** `docs/dataset/phase-7-recon-2026-09-19/outputs/q_ticks.out`
   found 15 of 72 pairs on a finer grid in 2026. Compare the recorded `pair_decimals` against those
   15 pairs and record whether they agree.

## Scope Limits

- One fetch. No polling, no schedule, no retention cache change.
- No other public or private endpoint. `TradeVolume` is not fetched here; the fee scenario is the
  operator's fixture.
- Do not edit `scripts/verify.py`. Re-pointing the Phase 2 candle criterion's tolerance at the
  recorded file is C's, in spec 141.
- The recorder, the recording manager and the funding poller keep running untouched.

## Check When Done

- The fixture parses with `clients/kraken/contracts.py`'s own pair-rules model, and every pair
  has `ordermin`, `costmin` and a tick size.
- The survivorship count and names are in the build log.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
