"""Runtime directory creation.

Spec 08 step 5. These are created once at startup, idempotently, before anything
tries to write into them. Creating a directory is not owning the runtime data
written into it: B's store writes ``data/db/`` and ``data/derived/``, C's
snapshots write ``data/derived/``, and every engine writes ``logs/``.

Everything here is ``pathlib``. The target OS is Windows and string
concatenation with ``/`` is a defect waiting for a path with a space in it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: The database file inside ``data/db/``.
#:
#: Named here because ``context/architecture-context.md`` documents the layout as
#: ``db/  acsoe.sqlite`` and nothing in the code said so — every caller until now
#: either took a path from a fixture or built one by hand. The daemon has to open
#: *the* database rather than *a* database, and the console will open the same one.
DB_FILENAME: Final = "acsoe.sqlite"


@dataclass(frozen=True)
class RuntimePaths:
    """The five directories the running system writes into.

    ``models/`` is deliberately absent: it is created by the training pipeline in
    Phase 5, which owns the run-id subdirectory naming, and creating it empty
    here would suggest a contract that does not exist yet.
    """

    root: Path
    raw: Path
    historical: Path
    derived: Path
    db: Path
    logs: Path

    def all(self) -> tuple[Path, ...]:
        return (self.raw, self.historical, self.derived, self.db, self.logs)


def runtime_paths(root: Path | None = None) -> RuntimePaths:
    """Resolve the runtime directory layout under ``root`` without creating anything."""
    base = (root or Path.cwd()).resolve()
    data = base / "data"
    return RuntimePaths(
        root=base,
        raw=data / "raw",
        historical=data / "historical",
        derived=data / "derived",
        db=data / "db",
        logs=base / "logs",
    )


def ensure_runtime_directories(root: Path | None = None) -> RuntimePaths:
    """Create the runtime directories if they are missing. Safe to call repeatedly.

    Idempotent by construction — ``mkdir(parents=True, exist_ok=True)`` — because
    this runs on every daemon start and a second start must not be an error.
    """
    paths = runtime_paths(root)
    for directory in paths.all():
        directory.mkdir(parents=True, exist_ok=True)
    return paths
