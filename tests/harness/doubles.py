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

import tempfile
from collections.abc import Iterator, Mapping
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

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._data[name]
        except KeyError as exc:
            raise AttributeError(f"config has no key {name!r}") from exc
        return MappingConfig(value) if isinstance(value, Mapping) else value

    def __contains__(self, name: str) -> bool:
        return name in self._data

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, Mapping) or part not in node:
                return default
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

    The temporary directory is held on the instance so it outlives the call and is
    cleaned up when the doubles are dropped.
    """

    config: MappingConfig
    clock: FixedClock
    clients: FakeClients
    _tmp: Any = None

    def close(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None


def build_verify_doubles() -> VerifyDoubles:
    """Build the doubles `orchestrator_empty_registry` runs a tick against.

    Called from `scripts/verify.py`, outside pytest, so it does its own temporary
    directory rather than leaning on `tmp_path`. Nothing is written under `data/`:
    every criterion has to pass on a fresh clone, and `data/` is gitignored.
    """
    tmp = tempfile.TemporaryDirectory(prefix="acsoe-verify-doubles-")
    store = migrated_store(Path(tmp.name) / "acsoe.sqlite")
    return VerifyDoubles(
        config=load_default_config(),
        clock=FixedClock(),
        clients=FakeClients(store=store),
        _tmp=tmp,
    )


def iter_repo_docs(root: Path = REPO_ROOT) -> Iterator[Path]:
    """The documents `docs_vocabulary` scans. Used by its tests."""
    yield root / "AGENTS.md"
    yield root / "README.md"
    yield from sorted((root / "context").glob("*.md"))
