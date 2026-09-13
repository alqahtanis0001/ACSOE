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
    """The six directories the running system writes into.

    ``models/`` joined them on 2026-09-13, spec 61 step 3. It was deliberately
    absent until then — the argument was that the training pipeline owns the
    run-id subdirectory naming, so creating the root empty would suggest a
    contract that did not exist yet. That contract exists now: B's
    :class:`~acsoe.clients.store.client.StoreClient` takes a ``models_dir`` and
    hands out ``models/<run_id>/`` through ``model_run_dir``, and engines 8, 13
    and 15 reach an artefact only that way.

    **Creating the root is A's; everything inside it is C's.** The same split as
    ``data/derived/``, which this module creates and B and C write into. The root
    is created empty on every start and stays empty on a fresh clone, which is
    the normal state: the three ``models.*_run_id`` keys are absent, the engines
    block, and the daemon still records market data. What this removes is the
    other failure — a store built with an artefact root that does not exist,
    refusing at the moment a gate needed it rather than at startup.
    """

    root: Path
    raw: Path
    historical: Path
    derived: Path
    db: Path
    logs: Path
    models: Path

    def all(self) -> tuple[Path, ...]:
        return (self.raw, self.historical, self.derived, self.db, self.logs, self.models)


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
        # A sibling of `data/` and `logs/`, not a child of `data/`. The layout in
        # `context/architecture-context.md` puts `models/` at the repository root,
        # and `data/` is what a rebuild may delete — a trained artefact is not
        # rebuildable from anything the archive holds.
        models=base / "models",
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
