"""The console's only write path. Spec 24.

Three names, one table, one row each. Everything else about this module is a
restriction rather than a feature, and each restriction is here because the
alternative breaks something specific.

**Exactly three names.** ``activate``, ``freeze`` and ``close_all``, from
:class:`~acsoe.clients.store.contracts.CommandName`. Anything else is a 404 that
writes nothing. **There is no fourth command.** The kill switch is ``close_all``
and there is no other mechanism — a "stop" or "shutdown" button is not in scope
and never will be, because a second way to end exposure is a second thing that
has to be proven to work in Phase 8.

**The console never stamps ``claimed_at``, ``claimed_by_run_id`` or
``consumed_at``.** Two-phase consumption is what stops a crash swallowing a kill
switch: the daemon's reader stamps ``claimed_at`` when it applies the effect and
``consumed_at`` only when the effect is complete, so a row claimed and not
consumed is an interrupted command that gets re-applied on the next startup. A
console that pre-stamped either would hand the daemon a command that looks
already done.

**The connection is its own, it is narrow, and it is enforced by SQLite rather
than by discipline.** ``console/reader.py``'s connection stays read-only and is
untouched by this module. The connection opened here is read-write and carries an
authorizer that refuses every write to every table but ``commands`` — so "touches
only the commands table" is a property the database enforces, not a claim about
what the code happens to call. `StoreClient` is B's and exposes writes for every
table; a subclass alone would have been a promise, and this is a guarantee.

**Nothing here constructs an exchange client or reads a credential.** The console
holds no credentials and can never place an order. It writes a row saying what
the operator asked for; the daemon decides what to do about it.

**A successful write means the command was *recorded*, not that the mode
*changed*.** The mode changes when the orchestrator claims the row at the top of
its next tick, and the status band shows it when it does. Saying otherwise would
make the console lie about the daemon's state — which is the one thing the band
exists not to do.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Final, Self

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.connection import open_connection
from acsoe.clients.store.contracts import CommandName, CommandRow, CommandSource, to_micros
from acsoe.platform.clock import Clock

__all__ = [
    "COMMAND_NAMES",
    "COMMAND_TABLE",
    "CONFIRMED_COMMANDS",
    "RECORDED_MESSAGE",
    "UNKNOWN_COMMAND_MESSAGE",
    "CommandWriter",
    "NarrowCommandStore",
    "command_label",
]

#: The three, and only the three. Read off `CommandName` rather than retyped, so
#: the enum and this endpoint cannot drift apart.
COMMAND_NAMES: Final[tuple[str, ...]] = tuple(name.value for name in CommandName)

#: The one table this module may write.
COMMAND_TABLE: Final = "commands"

#: Which commands need a confirmation before the row is written. `close_all` ends
#: exposure, so it is confirmed; the confirmation restates the action **by its own
#: name** and never renames it. `ui-context.md`: an action keeps its name through
#: the whole flow.
CONFIRMED_COMMANDS: Final[frozenset[str]] = frozenset({CommandName.CLOSE_ALL.value})

#: What each button says, and what the operator is told happened afterwards. The
#: label is the same word in both, which is the copy rule made mechanical.
_LABELS: Final[dict[str, str]] = {
    CommandName.ACTIVATE.value: "Activate",
    CommandName.FREEZE.value: "Freeze",
    CommandName.CLOSE_ALL.value: "Close all positions",
}

#: The message after a successful write. It says **recorded**, deliberately, and
#: says what happens next rather than claiming the state has changed.
RECORDED_MESSAGE: Final = (
    "{label} recorded. The daemon applies it at the top of its next tick, and the "
    "status band will show the new state when it does."
)

#: The message for a name that is not one of the three. It states what happened
#: and what the three names are. It does not apologise and it is not vague.
UNKNOWN_COMMAND_MESSAGE: Final = (
    "{name!r} is not a command. The console writes exactly three: {names}. Nothing "
    "was written."
)


def command_label(name: str) -> str:
    """The operator-facing name of a command. `Freeze` produces the state `Frozen`."""
    return _LABELS[name]


#: Mutating actions whose first authorizer argument names the table. SQLite calls
#: the authorizer with `(action, arg1, arg2, database, trigger)`; for every action
#: in this set `arg1` is the table, and `arg2` is the column on a row mutation and
#: unset on the DDL ones. Only `arg1` is inspected, so only `arg1` is named here.
_TABLE_WRITE_ACTIONS: Final[frozenset[int]] = frozenset(
    {
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_ALTER_TABLE,
    }
)

#: Actions with no table to check against that must not be reachable from here.
#: `ATTACH` is the one that matters: without it, a denied write could be routed
#: around by attaching the same file under another name.
_FORBIDDEN_ACTIONS: Final[frozenset[int]] = frozenset(
    {
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER,
    }
)


def _only_the_commands_table(
    action: int, arg1: str | None, _arg2: str | None, _db: str | None, _trigger: str | None
) -> int:
    """A SQLite authorizer that permits writes to `commands` and nothing else.

    Reads are left alone — this connection is allowed to read back the row it just
    wrote — and every mutating action is checked against the table it names. A
    write anywhere else is refused by the database engine itself, which no later
    refactoring inside this package can talk it out of. That is the difference
    between "touches only the commands table" being a claim and being a property.

    Bookkeeping actions carry no table name and are permitted: `SQLITE_TRANSACTION`
    and `SQLITE_PRAGMA` among them, because refusing those would refuse the commit
    that makes the insert durable and the pragmas `clients/store/connection.py`
    sets on every connection this project opens.
    """
    if action in _FORBIDDEN_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action in _TABLE_WRITE_ACTIONS and arg1 != COMMAND_TABLE:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class NarrowCommandStore(StoreClient):
    """B's store client over a connection that can only write `commands`.

    A subclass for the same reason `ReadOnlyStore` is one: every write the console
    needs already exists as `StoreClient.append_command`, `clients/store/` is B's
    directory, and a second `INSERT` written here would be a second statement of
    the schema that drifts the first time a column is added. Overriding where the
    connection comes from is the smallest change that makes the narrowness real.

    The connection itself comes from `clients/store/connection.open_connection`,
    not from a fresh `sqlite3.connect` — the WAL, autocommit and busy-timeout
    pragmas are B's and belong in one place. Two processes share this file and a
    connection opened without them would take the daemon's write lock in a way
    nothing else here does. The authorizer is installed afterwards, so those
    pragmas run before anything is being policed.
    """

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = open_connection(self._db_path)
            conn.set_authorizer(_only_the_commands_table)
            self._conn = conn
        return self._conn


class CommandWriter:
    """Appends one command row, and does nothing else to the system.

    Holds its own connection for the life of the process, like the reader does,
    and opens it lazily for the same reason: `acsoe console` has to start on a
    machine where the daemon has never run and the database file does not exist.
    """

    def __init__(self, db_path: Path, *, clock: Clock) -> None:
        self._store = NarrowCommandStore(Path(db_path))
        self._clock = clock

    @property
    def db_path(self) -> Path:
        return self._store.db_path

    @property
    def store(self) -> NarrowCommandStore:
        """The narrow client, for the negative test that attempts another write."""
        return self._store

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def append(self, name: str) -> CommandRow:
        """Write one unclaimed, unconsumed console command and return it.

        `created_at` and `updated_at` come from the injected clock in
        microseconds, which is the store's own unit. The three stamping fields are
        left null: the daemon's reader owns them.
        """
        if name not in COMMAND_NAMES:
            raise ValueError(f"{name!r} is not one of {COMMAND_NAMES}")
        now = to_micros(self._clock.now())
        row = CommandRow(
            command=name,
            source=CommandSource.CONSOLE,
            created_at=now,
            claimed_at=None,
            claimed_by_run_id=None,
            consumed_at=None,
            updated_at=now,
        )
        row_id = self._store.append_command(row)
        return row.model_copy(update={"id": row_id})
