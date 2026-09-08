# Agent B — Store and trading

## Claimed

- **Spec 11** — `db/migrations/`, SQLite schema and forward-only migration runner. *In progress.*
- **Spec 12** — `src/acsoe/clients/store/`, store client and contracts. *Claimed, blocked on 11.*
- **Spec 13** — `src/acsoe/clients/store/seed.py`, seed generator. *Claimed, blocked on 12.*

## Status

Starting from an empty tree: no `src/`, no `db/`, no `scripts/`, no `config/`, no
`pyproject.toml`. Building 11 first because it blocks 12, which blocks 13, which blocks
C's `seed_fixtures_present` criterion and everything Phase 3 tests `safety` against.

## Open questions

*(see also the escalations sent to the lead)*

### 1. `is_primary` uniqueness must be scoped by `run_id`, not `cycle_id` alone — RESOLVED by reading, escalated for confirmation

Spec 11 step 5 says "partial unique index on `(cycle_id)` where `is_primary` is true".
Taken literally that is unimplementable alongside spec 13 step 3, which requires the seeded
outage run to span **two `run_id`s** so that the `ts` ordering is actually exercised.
`cycle_id` "is minted per tick within a run and restarts with the process"
(`architecture-context.md`), so two runs necessarily reuse the same low `cycle_id` values —
and if they did not overlap, ordering by `cycle_id` would give the same answer as ordering
by `ts` and the Phase 3 criterion would prove nothing.

Implemented as a partial unique index on `(run_id, cycle_id) WHERE is_primary = 1`. This
satisfies the stated intent ("two engines each claiming to be the one that gated the
opportunity chain" is impossible **for a tick**) and the acceptance check (a second primary
insert for the same `cycle_id` within a run raises). Escalated to the lead.

### 2. `safety` threshold key names not yet fixed in `config/default.yaml`

Spec 06 names `safety.max_consecutive_data_blocks: 15` but only describes "the drawdown
limit, loss-streak limit and error-rate window" without naming them. The seed has to exceed
each of them by name. Proposed to the lead, and used as the seed's documented defaults until
the lead confirms:

| Key | Proposed default | Seed produces |
|---|---|---|
| `safety.max_consecutive_data_blocks` | 15 | 18 consecutive `data_guard` ticks |
| `safety.max_drawdown_pct` | 0.10 | drawdown of 0.18 at the trough |
| `safety.max_consecutive_losses` | 5 | 7 consecutive losing closed trades |
| `safety.error_rate_window_s` | 3600 (fixed by `architecture-context.md`: "trailing hour") | — |
| `safety.max_errors_in_window` | 10 | 12 `status='ERROR'` block records in the window |

The seed does not read `config/default.yaml`; it takes a `SeedThresholds` dataclass so a
Phase 3 test can seed against whatever the config actually says. The defaults above are the
fallback, and the seed always overshoots each threshold rather than sitting on it.

## Blocked on

- **A (`pyproject.toml`, package skeleton, spec 03)** — `src/acsoe/__init__.py` and
  `src/acsoe/clients/__init__.py` are A's per spec 03 step 4. Proceeding under implicit
  namespace packages so nothing idles; my own `src/acsoe/clients/store/__init__.py` is mine.
- **C (`scripts/verify.py`, spec 00–02)** — cannot run the fourth verification command until
  it exists.
- **Lead (`config/default.yaml`, spec 06)** — see open question 2.
