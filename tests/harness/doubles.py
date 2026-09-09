"""Shared test doubles: the clock, the config, the client bundle, and `state`.

Spec 14 step 2. One definition of each, so every agent's tests agree on what a
fixed clock or an empty `state` looks like - and so `scripts/verify.py` can build
an `orchestrator_empty_registry` tick out of the same objects the tests use rather
than a second, subtly different set.

Two of these are provisional in a way worth stating out loud. `Clock` and `Config`
are Protocols the lead declares in `core/contracts.py`, which does not exist yet;
`FixedClock` and `MappingConfig` are built to the shape the contract implies and
will be re-pointed at the real declaration the moment it lands. The seam is
recorded in `context/progress/c-interface.md`.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tests.harness.fake_kraken import FakeKrakenClient, FakeRecorder

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"

# A fixed instant, deliberately not "now". Every test that needs a timestamp uses
# this one, so two runs of the same test produce byte-identical output - which is
# what makes a replay faithful and a seeded database comparable.
FIXED_NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

__all__ = [
    "FIXED_NOW",
    "FakeClients",
    "FixedClock",
    "MappingConfig",
    "VerifyDoubles",
    "build_verify_doubles",
    "fresh_state",
    "load_default_config",
]


class FixedClock:
    """An injected clock that never moves unless a test moves it.

    Invariant 9: engines receive `context.now` and never read a clock. The
    orchestrator holds the only `Clock` in the system, so this is the only place a
    test ever needs one.
    """

    def __init__(self, start: datetime = FIXED_NOW) -> None:
        if start.tzinfo is None:
            raise ValueError("a naive datetime is never acceptable; UTC only")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> datetime:
        self._now = self._now + timedelta(seconds=seconds)
        return self._now

    def set(self, moment: datetime) -> datetime:
        if moment.tzinfo is None:
            raise ValueError("a naive datetime is never acceptable; UTC only")
        self._now = moment.astimezone(UTC)
        return self._now


class MappingConfig:
    """Attribute and dotted access over a parsed configuration mapping.

    It wraps `config/default.yaml` verbatim, **including its nulls**. Several
    thresholds there are marked OPERATOR REQUIRED and are `null` until the operator
    sets them; this deliberately does not fill them in. Inventing a hurdle multiple
    or a drawdown limit to make a fixture convenient would be inventing trading
    behaviour, which `AGENTS.md` forbids outright - and a test asserting against an
    invented threshold proves nothing anyway. A test that needs a threshold passes
    it explicitly, the way B's `SeedThresholds` does.
    """

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)

    @property
    def mode(self) -> Any:
        """Declared explicitly, not reached through `__getattr__`.

        This looks redundant - `__getattr__` already answers `config.mode` - and it
        is not. Since Python 3.12, `isinstance(x, SomeRuntimeCheckableProtocol)`
        resolves each member with `inspect.getattr_static`, which walks the class
        dictionary and the MRO and deliberately never calls `__getattr__`. A double
        that supplies `mode` dynamically therefore *works* everywhere it is used and
        still reports `isinstance(config, Config) is False`, with no error to read.

        `mode` is also the one field `core/contracts.py` pins by name, so writing it
        out is honest rather than merely expedient.
        """
        try:
            return self._data["mode"]
        except KeyError as exc:
            raise AttributeError("config has no key 'mode'") from exc

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._data[name]
        except KeyError as exc:
            raise AttributeError(f"config has no key {name!r}") from exc
        return MappingConfig(value) if isinstance(value, Mapping) else value

    def __contains__(self, name: str) -> bool:
        return name in self._data

    def get(self, dotted: str, /) -> Any:
        """Look a value up by dotted path. **Raises** when the key is absent.

        Raising is the contract, not an opinion: `core/contracts.py` says "a missing
        configuration key is a defect, and an engine silently receiving `None` for a
        threshold is exactly the failure this project refuses to allow". An earlier
        version of this double took a `default` and returned it, which made the fake
        kinder than the real `platform/config.py` - and a fake kinder than reality
        hides fail-closed bugs, which is the one thing a test double must never do.

        A key that is *present* and `null` still returns `None`. That is a different
        state and deliberately not an error: the lead writes OPERATOR REQUIRED
        thresholds as `null`, and "the operator has not decided yet" is not the same
        as "this key does not exist".
        """
        node: Any = self._data
        for index, part in enumerate(dotted.split(".")):
            if not isinstance(node, Mapping) or part not in node:
                reached = ".".join(dotted.split(".")[:index]) or "(root)"
                raise KeyError(
                    f"config has no key {dotted!r}; {part!r} is not present under {reached}"
                )
            node = node[part]
        return node

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"MappingConfig({sorted(self._data)})"


def load_default_config(path: Path = DEFAULT_CONFIG_PATH) -> MappingConfig:
    """Parse `config/default.yaml`. `safe_load` only - never `yaml.load`."""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    if data.get("mode") != "paper":
        raise ValueError(
            f"{path} has mode={data.get('mode')!r}. Paper is the default in every config "
            "file, fixture and example - invariant 1."
        )
    return MappingConfig(data)


@dataclass
class FakeClients:
    """The three injected clients of engine contract rule 4.

    `store` is B's real `StoreClient` against a temporary migrated database rather
    than a hand-written fake: the fake would be a second implementation of a schema
    the store already owns, and it would drift.
    """

    kraken: FakeKrakenClient = field(default_factory=FakeKrakenClient)
    store: Any = None
    recorder: FakeRecorder = field(default_factory=FakeRecorder)


def fresh_state() -> dict[str, Any]:
    """A `state` dict as the orchestrator hands it to the first engine of a tick.

    `state` is fresh every tick; only `state["system"]` carries across, and mode
    always starts `idle` - it is never restored from the store, so a daemon that
    crashed while trading comes back not trading. `guard_blockers` is an empty list
    on an unblocked tick, never absent.
    """
    return {
        "system": {"mode": "idle", "close_intent": False},
        "cycle_id": 1,
        "guard_blockers": [],
    }


def migrated_store(db_path: Path) -> Any:
    """B's real store client against a migrated database, or None if unavailable."""
    try:
        from acsoe.clients.store.client import StoreClient
    except ModuleNotFoundError:
        return None
    client = StoreClient(db_path)
    client.migrate()
    return client


@dataclass
class VerifyDoubles:
    """What `scripts/verify.py` needs to run one orchestrator tick.

    The temporary directory is held on the instance so it outlives the call, and
    :meth:`close` releases it. **The store is closed before the directory is
    removed, and the removal is best-effort.** Both halves are load-bearing on
    Windows: SQLite holds the file open until the connection is closed, so a
    directory removed first raises `PermissionError [WinError 32]` - which is
    exactly what `verify.py --phase 0` printed above its report on every run,
    green ones included, out of `TemporaryDirectory`'s finalizer where nothing
    could catch it. Failing to delete a throwaway database is not a verdict about
    anything, so it is swallowed rather than raised at a caller who is checking
    the orchestrator.
    """

    config: MappingConfig
    clock: FixedClock
    clients: FakeClients
    _tmp: Any = None

    def close(self) -> None:
        store = self.clients.store
        closer = getattr(store, "close", None)
        if callable(closer):
            with suppress(Exception):
                closer()
        self.clients.store = None
        if self._tmp is not None:
            path = Path(self._tmp.name)
            # Disarm the finalizer before removing the tree ourselves: its cleanup
            # is the thing that raised, and it runs at collection with no caller.
            with suppress(Exception):
                self._tmp._finalizer.detach()
            shutil.rmtree(path, ignore_errors=True)
            self._tmp = None


def build_verify_doubles() -> VerifyDoubles:
    """Build the doubles `orchestrator_empty_registry` runs a tick against.

    Called from `scripts/verify.py`, outside pytest, so it does its own temporary
    directory rather than leaning on `tmp_path`. Nothing is written under `data/`:
    every criterion has to pass on a fresh clone, and `data/` is gitignored.

    The caller owns the result and must call :meth:`VerifyDoubles.close`.
    """
    tmp = tempfile.TemporaryDirectory(prefix="acsoe-verify-doubles-")
    doubles = VerifyDoubles(
        config=load_default_config(),
        clock=FixedClock(),
        clients=FakeClients(),
        _tmp=tmp,
    )
    try:
        doubles.clients.store = migrated_store(Path(tmp.name) / "acsoe.sqlite")
    except Exception:
        # The directory is already made, so anything raised past this point leaks it
        # - and a criterion pointed at a fabricated tree raises here routinely,
        # because a store that exists and does not answer `migrate()` is exactly the
        # subject some of those criteria are judging.
        doubles.close()
        raise
    return doubles


def iter_repo_docs(root: Path = REPO_ROOT) -> Iterator[Path]:
    """The documents `docs_vocabulary` scans. Used by its tests."""
    yield root / "AGENTS.md"
    yield root / "README.md"
    yield from sorted((root / "context").glob("*.md"))
