# 24 — Activate, Freeze and Close all

**Owner:** C — Interface and models

## Goal

The console's only write path: three buttons that append one correct row each to the `commands`
table, and do nothing else to the system.

## Implementation

1. Create `src/acsoe/console/commands.py` and mount `POST /api/command/{name}` for exactly three
   names: `activate`, `freeze`, `close_all`. Any other name is a 404 and writes no row.
2. Each writes **one** `CommandRow` through `StoreClient.append_command`, with
   `source = CommandSource.console`, `created_at` in microseconds, and `claimed_at`,
   `claimed_by_run_id` and `consumed_at` all null. The daemon's reader in `core/` stamps those;
   the console never does.
3. This is the console's only write. It uses its own narrow read-write connection and touches
   **only** the `commands` table — spec 17's reader connection stays read-only.
4. Buttons say what happens: `Activate`, `Freeze`, `Close all positions`. Never `Submit`. An
   action keeps its name through the whole flow — `Freeze` produces the state `Frozen`.
5. `close_all` gets a confirmation step, because it ends exposure. The confirmation restates the
   action by its own name and never renames it.
6. After a successful write the UI reflects that the command was *recorded*, not that the mode
   *changed*. The mode changes when the orchestrator claims the row at the top of its next tick,
   and the status band will show it when it does. Claiming the two are the same thing would make
   the console lie about the daemon's state.
7. Errors state what happened and what to do. They never apologise and are never vague.

## Scope Limits

- Do **not** apply the effect. The console never writes `state["system"]`; the command reader in
  `src/acsoe/core/` is the only writer of it and belongs to the lead.
- Do **not** stamp `claimed_at`, `claimed_by_run_id` or `consumed_at`. Two-phase consumption is
  what stops a crash swallowing a kill switch, and a console that pre-stamps it breaks that.
- **Do not add a fourth command.** The kill switch is `close_all` and there is no other
  mechanism. A "stop" or "shutdown" button is not in scope and never will be.
- Do **not** construct a Kraken client, read a credential, or place an order. The console holds
  no credentials and can never place an order — that is a property of the process, and the
  console package must not import `clients/kraken/` at all.
- Do **not** write to any table other than `commands`.
- Do **not** send the command over the WebSocket; the socket is read-only.
- Do **not** change `src/acsoe/core/`, `bootstrap.py`, or the store client. Those are the lead's
  and B's.

## Check When Done

- Three tests, one per command: each `POST` writes exactly one row with the right `command`,
  `source = 'console'`, and null `claimed_at`/`consumed_at`.
- An unrecognised command name returns 404 and writes no row.
- A row written here is claimed and consumed unchanged by the orchestrator's existing command
  reader — asserted against the real reader, not a mock of it.
- The reader connection still refuses a write after the command path has been exercised.
- `close_all` requires the confirmation step, and the button text is unchanged by it.
- The console package imports nothing from `clients/kraken/` — one test asserting exactly that.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 1`
