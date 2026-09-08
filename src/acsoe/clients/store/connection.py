"""SQLite connection setup, in one place.

Every connection this package opens comes from here, so the pragmas that matter are
not a thing each call site remembers or forgets.

WAL is not an optimisation. `ui-context.md` has the daemon and the console running as
two separate processes against one database file, the console polling a watermark
while the daemon writes; the default rollback journal would have them blocking each
other on every tick.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_BUSY_TIMEOUT_MS = 5_000


def open_connection(
    db_path: Path,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    """Open a connection with this project's pragmas applied.

    `isolation_level=None` turns off the driver's implicit transaction handling so
    that transactions are explicit and visible at the call site rather than implied
    by which statement happened to run first.
    """
    db_path = Path(db_path)
    parent = db_path.parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    return conn


def close_connection(conn: sqlite3.Connection) -> bool:
    """Checkpoint the write-ahead log and close. Returns whether the checkpoint ran.

    The truncating checkpoint matters for spec 13's byte-identical requirement: it
    folds every page back into the main database file and empties the `-wal`
    sidecar, so two seedings of the same seed produce the same bytes rather than
    the same bytes plus whatever happened to still be in a log.

    A checkpoint can legitimately fail while another connection holds a read lock,
    and that is not a reason to leave this connection open — nor is it data loss,
    because the rows are already committed in the log and every reader that opens
    the database normally still sees them. But it is not nothing either: the `-wal`
    sidecar outlives the connection, and a caller that cares about the file itself
    should be able to find out. Hence a return value rather than a silent swallow;
    a caller that does not care may ignore it, and :meth:`StoreClient.close` does.
    """
    checkpointed = True
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.DatabaseError:
        checkpointed = False
    conn.close()
    return checkpointed
