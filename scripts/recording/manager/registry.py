"""``sources.yaml``: who records, where, and when they were last known good.

Plain YAML, hand-editable, and the manager preserves keys it does not recognise
so a comment or a field somebody added by hand survives a rewrite.

**The important rule in this file is about `last_seen`.** It is never used to
decide that a source is dead. For a server node it records the last *successful
check*; for a standalone node it records the last *import*; for the master it is
now. A standalone node that has not been imported for a week may be recording
perfectly, and the manager says "no live status" rather than guessing. Silence is
not evidence.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import yaml

KIND_MASTER: Final = "master"
KIND_SERVER: Final = "server"
KIND_STANDALONE: Final = "standalone"
KINDS: Final = (KIND_MASTER, KIND_SERVER, KIND_STANDALONE)

#: The default way to list a remote archive. `{archive}` is substituted. It is a
#: field rather than a constant because a Windows server node answers `dir /b`
#: and a Linux one answers `ls -1`, and guessing wrong produces an empty listing
#: that looks exactly like an empty archive.
DEFAULT_LIST_COMMAND: Final = "ls -1 {archive}"

DEFAULT_SSH_PORT: Final = 22

SOURCE_ID_ALLOWED: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
)


class RegistryError(RuntimeError):
    """The registry cannot be read or a source cannot be registered."""


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitise_source_id(raw: str) -> str:
    """The same rule `record.py` applies, because it is the same identity.

    The source id is in every filename the node writes, so the manager must not
    register an id the recorder would then fold into something else — that splits
    one source into two everywhere it is counted.
    """
    folded = "".join(char if char in SOURCE_ID_ALLOWED else "-" for char in raw.strip())
    while "--" in folded:
        folded = folded.replace("--", "-")
    folded = folded.strip("-.").lower()[:48]
    if not folded:
        raise RegistryError(
            f"{raw!r} contains nothing usable as a source id. It becomes part of every "
            f"filename the node writes, so it has to survive being one."
        )
    return folded


class Source:
    """One registered source.

    Not a ``@dataclass``. These modules are loaded by path in the tests, which
    leaves them absent from ``sys.modules`` where ``dataclasses`` looks its own
    module up; the decorator then raises ``AttributeError`` at import and the
    failure lands in a fixture rather than in a test. Same note as ``PairStat`` in
    ``scripts/record.py``.
    """

    __slots__ = ("raw",)

    def __init__(self, raw: dict[str, Any]) -> None:
        #: The whole mapping as it appeared in the file, so a rewrite keeps every
        #: key this class has never heard of.
        self.raw = dict(raw)

    # -- identity ----------------------------------------------------------- #

    @property
    def id(self) -> str:
        return str(self.raw.get("id", "")).strip()

    @property
    def kind(self) -> str:
        kind = str(self.raw.get("kind", "")).strip().lower()
        return kind if kind in KINDS else KIND_STANDALONE

    @property
    def note(self) -> str:
        return str(self.raw.get("note", "") or "").strip()

    # -- where its data is -------------------------------------------------- #

    @property
    def archive_dir(self) -> str | None:
        value = self.raw.get("archive_dir")
        return str(value) if isinstance(value, str) and value.strip() else None

    @property
    def summary_dir(self) -> str | None:
        value = self.raw.get("summary_dir")
        return str(value) if isinstance(value, str) and value.strip() else None

    # -- how to reach it ---------------------------------------------------- #

    @property
    def ssh_host(self) -> str | None:
        value = self.raw.get("ssh_host")
        return str(value) if isinstance(value, str) and value.strip() else None

    @property
    def ssh_port(self) -> int:
        value = self.raw.get("ssh_port", DEFAULT_SSH_PORT)
        return value if isinstance(value, int) and value > 0 else DEFAULT_SSH_PORT

    @property
    def ssh_key(self) -> str | None:
        value = self.raw.get("ssh_key")
        return str(value) if isinstance(value, str) and value.strip() else None

    @property
    def list_command(self) -> str:
        value = self.raw.get("list_command")
        return value if isinstance(value, str) and value.strip() else DEFAULT_LIST_COMMAND

    @property
    def reachable(self) -> bool:
        """Whether the master can go and look, right now, without a person.

        The master reaches into a server. Nothing reaches into a standalone node,
        and nothing reaches into the master from outside at all.
        """
        return self.kind == KIND_SERVER and self.ssh_host is not None

    # -- what is known about it --------------------------------------------- #

    @property
    def last_seen(self) -> str | None:
        return _iso_or_none(self.raw.get("last_seen"))

    @property
    def last_check(self) -> str | None:
        return _iso_or_none(self.raw.get("last_check"))

    @property
    def last_check_ok(self) -> bool | None:
        value = self.raw.get("last_check_ok")
        return value if isinstance(value, bool) else None

    @property
    def last_check_error(self) -> str | None:
        value = self.raw.get("last_check_error")
        return str(value) if isinstance(value, str) and value.strip() else None

    @property
    def last_import(self) -> str | None:
        return _iso_or_none(self.raw.get("last_import"))

    @property
    def last_import_dates(self) -> list[str]:
        value = self.raw.get("last_import_dates")
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, str)]

    def update(self, **fields: Any) -> None:
        """Merge fields in. A `None` clears the key rather than storing a null."""
        for key, value in fields.items():
            if value is None:
                self.raw.pop(key, None)
            else:
                self.raw[key] = value


def _iso_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, datetime):
        # PyYAML parses an unquoted ISO timestamp into a datetime, so a file
        # edited by hand can carry either. Normalised on the way out rather than
        # on the way in, so a rewrite does not reformat somebody's text.
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


class Registry:
    """The whole of ``sources.yaml``."""

    __slots__ = ("_document", "path")

    def __init__(self, path: Path, document: dict[str, Any]) -> None:
        self.path = path
        self._document = document

    # -- reading ------------------------------------------------------------ #

    @classmethod
    def load(cls, path: Path) -> Registry:
        """Read the file, or start an empty registry if it is not there yet.

        A missing registry is a first run, not an error. A *malformed* one is an
        error and is raised: silently starting fresh over a file somebody has been
        editing would lose every node they had registered.
        """
        if not path.is_file():
            return cls(path, {"version": 1, "sources": []})
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise RegistryError(f"{path} is not valid YAML: {exc}") from exc
        if loaded is None:
            return cls(path, {"version": 1, "sources": []})
        if not isinstance(loaded, dict):
            raise RegistryError(f"{path} should be a mapping with a `sources:` list")
        sources = loaded.get("sources")
        if sources is None:
            loaded["sources"] = []
        elif not isinstance(sources, list):
            raise RegistryError(f"{path}: `sources:` should be a list")
        return cls(path, loaded)

    @property
    def sources(self) -> list[Source]:
        raw = self._document.get("sources", [])
        return [Source(item) for item in raw if isinstance(item, dict) and item.get("id")]

    def get(self, source_id: str) -> Source | None:
        for source in self.sources:
            if source.id == source_id:
                return source
        return None

    def require(self, source_id: str) -> Source:
        source = self.get(source_id)
        if source is None:
            known = ", ".join(item.id for item in self.sources) or "none"
            raise RegistryError(f"no source called {source_id!r}. Registered: {known}.")
        return source

    # -- writing ------------------------------------------------------------ #

    def add(self, **fields: Any) -> Source:
        source_id = sanitise_source_id(str(fields.get("id", "")))
        if self.get(source_id) is not None:
            raise RegistryError(
                f"a source called {source_id!r} is already registered. Source ids are in "
                f"every filename, so two machines sharing one would merge into a single "
                f"apparent source and their overlapping days would collide."
            )
        kind = str(fields.get("kind", "")).strip().lower()
        if kind not in KINDS:
            raise RegistryError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}")
        entry: dict[str, Any] = {key: value for key, value in fields.items() if value is not None}
        entry["id"] = source_id
        entry["kind"] = kind
        entry.setdefault("created", utc_now_iso())
        self._document.setdefault("sources", []).append(entry)
        return Source(entry)

    def update(self, source_id: str, **fields: Any) -> Source:
        for item in self._document.get("sources", []):
            if isinstance(item, dict) and item.get("id") == source_id:
                source = Source(item)
                source.update(**fields)
                item.clear()
                item.update(source.raw)
                return source
        raise RegistryError(f"no source called {source_id!r}")

    def save(self) -> None:
        """Write the file atomically.

        Written to a temporary file in the same directory and renamed over the
        original, so an interrupted write leaves the previous registry intact
        rather than a half file. The registry is the only record of how to reach
        a node; losing it means finding the machines again by hand.
        """
        self._document.setdefault("version", 1)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(self._document, sort_keys=False, allow_unicode=True, width=88)
        descriptor, temporary = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=self.path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary).replace(self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
