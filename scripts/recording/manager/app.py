"""The manager application: five screens over the archive, the registry and SSH.

It reads files and runs `ssh`. **It never records**, so it never competes for an
archive lock, and **it never writes to the SQLite store** — engine 19 `memory` is
the single writer of every relational row and nothing here goes near it. The only
things it writes are `sources.yaml`, the staging directory, files it has verified
into the archive, and node packages.

## The honesty rule, which is the whole design

Three kinds of source, three different qualities of knowledge, and the UI never
levels them up into one green light:

* **master** — local disk. Status is read directly and is current.
* **server** — over SSH. Status is as fresh as the last check, and the screen says
  *when* that check was. A failed check reports the error verbatim and the source
  is shown as **not reachable**, which is a statement about the network and not
  about the recorder.
* **standalone** — no route at all. **No live status, ever.** It reports the last
  import and the dates it covered. A standalone node that has said nothing for a
  week may be recording perfectly, and reporting it as dead on the strength of
  silence is a guess dressed as a fact — one that gets a working recorder switched
  off.

Every status payload therefore carries `liveness`, which is one of `live`,
`as_of`, `unreachable` or `none`, and the page renders those four differently.
There is no boolean anywhere that collapses them.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from recording.manager import archive as archive_mod
from recording.manager import node_package, ssh, staging
from recording.manager.registry import (
    KIND_MASTER,
    KIND_SERVER,
    KIND_STANDALONE,
    Registry,
    RegistryError,
    Source,
    sanitise_source_id,
    utc_now_iso,
)

HERE: Final = Path(__file__).resolve().parent
REPO_ROOT: Final = HERE.parents[2]
RECORDING_DIR: Final = HERE.parent

DEFAULT_REGISTRY: Final = RECORDING_DIR / "sources.yaml"
DEFAULT_STAGING: Final = REPO_ROOT / "data" / "staging"
DEFAULT_INBOX: Final = REPO_ROOT / "data" / "inbox"
DEFAULT_NODES_DIR: Final = REPO_ROOT / "data" / "nodes"
DEFAULT_ARCHIVE: Final = REPO_ROOT / "data" / "raw"
DEFAULT_CACHE: Final = RECORDING_DIR / archive_mod.CACHE_FILENAME

HEARTBEAT_GLOB: Final = "heartbeat__*.ndjson"
LOCK_FILENAME: Final = ".recorder.lock"

#: Where the master's SSH public key is looked for when packaging a server node.
KEY_CANDIDATES: Final = (
    Path("~/.ssh/acsoe_node.pub"),
    Path("~/.ssh/id_ed25519.pub"),
    Path("~/.ssh/id_rsa.pub"),
)

#: How long a heartbeat may be silent before the master's own status stops
#: reading "recording". Three beats at the recorder's default of one a minute:
#: one missed beat is a scheduling hiccup, three is a process that is gone.
MASTER_STALE_S: Final = 200.0


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #


class PullRequest(BaseModel):
    source_id: str
    dry_run: bool = False


class InboxRequest(BaseModel):
    dry_run: bool = False


class CreateNodeRequest(BaseModel):
    source_id: str
    kind: str = Field(default=KIND_STANDALONE)
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_key: str | None = None
    archive_dir: str = node_package.DEFAULT_NODE_ARCHIVE
    remote_archive_dir: str | None = None


# --------------------------------------------------------------------------- #
# Reading a local archive for status
# --------------------------------------------------------------------------- #


def _last_record(path: Path, *, tail: int = 256 * 1024) -> dict[str, Any] | None:
    import json

    try:
        size = path.stat().st_size
        if size == 0:
            return None
        with path.open("rb") as handle:
            handle.seek(max(0, size - tail))
            chunk = handle.read()
    except OSError:
        return None
    for raw in reversed(chunk.split(b"\n")):
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _age_of(record: dict[str, Any] | None, *, now: datetime) -> float | None:
    if record is None:
        return None
    for key in ("ts_recv", "ts", "minute"):
        value = record.get(key)
        if isinstance(value, str) and value:
            try:
                moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            return max(0.0, (now - moment).total_seconds())
    return None


def local_status(directory: Path, *, now: datetime) -> dict[str, Any]:
    """What a directory on this machine says about the recorder writing into it."""
    if not directory.is_dir():
        return {
            "exists": False,
            "detail": f"{directory} does not exist",
            "archive_age_s": None,
            "heartbeat_age_s": None,
        }
    files = [path for path in directory.glob("*.jsonl") if path.is_file()]
    newest = max(files, key=lambda path: path.stat().st_mtime, default=None)
    beats = [path for path in directory.glob(HEARTBEAT_GLOB) if path.is_file()]
    newest_beat = max(beats, key=lambda path: path.stat().st_mtime, default=None)
    beat = _last_record(newest_beat) if newest_beat is not None else None
    return {
        "exists": True,
        "detail": None,
        "file": newest.name if newest is not None else None,
        "size_bytes": newest.stat().st_size if newest is not None else 0,
        "archive_age_s": _age_of(_last_record(newest), now=now) if newest is not None else None,
        "heartbeat_age_s": _age_of(beat, now=now),
        "heartbeat_pairs": beat.get("pair_count") if beat else None,
        "heartbeat_connected": beat.get("connected") if beat else None,
        "heartbeat_stopping": bool(beat.get("stopping")) if beat else None,
        "lock_present": (directory / LOCK_FILENAME).exists(),
        "free_bytes": _free_bytes(directory),
    }


def _free_bytes(directory: Path) -> int | None:
    try:
        return shutil.disk_usage(directory).free
    except OSError:  # pragma: no cover - the directory exists by construction
        return None


def master_liveness(status: dict[str, Any]) -> tuple[str, str]:
    """``(liveness, one honest sentence)`` for the master's own archive."""
    if not status["exists"]:
        return "none", status["detail"] or "the archive directory is not there"
    beat = status.get("heartbeat_age_s")
    age = status.get("archive_age_s")
    if status.get("heartbeat_stopping"):
        return "none", "the recorder stopped cleanly; its last heartbeat said so"
    if beat is None and age is None:
        return "none", "nothing has been written here and there is no heartbeat"
    if beat is not None and beat > MASTER_STALE_S:
        return "unreachable", f"the heartbeat is {beat / 60:.0f} minutes old — the recorder is gone"
    if beat is None and age is not None and age > MASTER_STALE_S:
        return (
            "unreachable",
            f"nothing written for {age / 60:.0f} minutes, and this recorder writes no heartbeat",
        )
    if age is not None and beat is not None and age > MASTER_STALE_S >= beat:
        return "live", (
            "alive but receiving nothing: the recorder is beating and no market data has "
            "landed. A subscription has died or the socket is down."
        )
    return "live", "recording"


# --------------------------------------------------------------------------- #
# The application
# --------------------------------------------------------------------------- #


def create_app(
    *,
    registry_path: Path | None = None,
    archive_dir: Path | None = None,
    staging_dir: Path | None = None,
    inbox_dir: Path | None = None,
    nodes_dir: Path | None = None,
    repo_root: Path | None = None,
    cache_path: Path | None = None,
) -> FastAPI:
    """Build the app. Every path is injected so a test does not touch real data."""
    paths = {
        "registry": registry_path or DEFAULT_REGISTRY,
        "archive": archive_dir or DEFAULT_ARCHIVE,
        "staging": staging_dir or DEFAULT_STAGING,
        "inbox": inbox_dir or DEFAULT_INBOX,
        "nodes": nodes_dir or DEFAULT_NODES_DIR,
        "repo": repo_root or REPO_ROOT,
        "cache": cache_path or DEFAULT_CACHE,
    }

    app = FastAPI(title="ACSOE Recording Manager", docs_url=None, redoc_url=None)
    app.state.paths = paths

    static = HERE / "static"
    if static.is_dir():
        app.mount("/static", StaticFiles(directory=str(static)), name="static")

    def registry() -> Registry:
        return Registry.load(paths["registry"])

    def now() -> datetime:
        return datetime.now(UTC)

    # -- the page ----------------------------------------------------------- #

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse((HERE / "templates" / "index.html").read_text(encoding="utf-8"))

    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse(
            {
                "manager": "ready",
                "archive": paths["archive"].as_posix(),
                "registry": paths["registry"].as_posix(),
                "ssh_available": ssh.have_ssh(),
                "scp_available": ssh.have_scp(),
                "writes_to_store": False,
                "records": False,
            }
        )

    # -- SOURCES ------------------------------------------------------------ #

    @app.get("/api/sources")
    def sources(check: bool = False) -> JSONResponse:
        """Every registered source with an honest status.

        `check=true` actually reaches out over SSH, which takes seconds per server
        node and is therefore never done on a page load. Without it, a server
        node reports the result of the last check *and when that was*, which is a
        different and weaker claim than "it is up", and is rendered differently.
        """
        moment = now()
        reg = registry()
        out: list[dict[str, Any]] = []
        for source in reg.sources:
            out.append(_source_payload(source, reg, paths=paths, now=moment, check=check))
        if check:
            reg.save()
        return JSONResponse(
            {
                "checked_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "live_check_performed": check,
                "sources": out,
            }
        )

    # -- COVERAGE and GAPS -------------------------------------------------- #

    @app.get("/api/coverage")
    def coverage() -> JSONResponse:
        cache = archive_mod.Cache(paths["cache"])
        files = archive_mod.scan_directory(paths["archive"], cache=cache)
        cache.save()
        grid = archive_mod.build_grid(files)
        grid["archive_dir"] = paths["archive"].as_posix()
        grid["file_count"] = len(files)
        return JSONResponse(grid)

    @app.get("/api/gaps")
    def gaps() -> JSONResponse:
        cache = archive_mod.Cache(paths["cache"])
        files = archive_mod.scan_directory(paths["archive"], cache=cache)
        cache.save()
        grid = archive_mod.build_grid(files)
        report = archive_mod.find_gaps(grid)
        report["archive_dir"] = paths["archive"].as_posix()
        return JSONResponse(report)

    # -- IMPORT ------------------------------------------------------------- #

    @app.post("/api/import/pull")
    def pull(body: PullRequest) -> JSONResponse:
        """Fetch day files a server node holds and the master does not.

        Everything lands in staging and is verified there. Today's file is never
        pulled: it is open on the node and being appended to, so what arrives is a
        prefix of a day rather than a day, and it would then collide with the real
        file tomorrow and be refused — after transferring a gigabyte.
        """
        reg = registry()
        try:
            source = reg.require(body.source_id)
        except RegistryError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        if source.kind != KIND_SERVER or not source.ssh_host:
            return JSONResponse(
                {
                    "error": (
                        f"{source.id} is a {source.kind} node. There is no route from the "
                        f"master to it, by design — a standalone node is collected by a "
                        f"person and imported with Check inbox."
                    )
                },
                status_code=400,
            )

        remote_dir = source.archive_dir or node_package.DEFAULT_NODE_ARCHIVE
        try:
            names, listing = ssh.list_files(
                host=source.ssh_host,
                archive_dir=remote_dir,
                list_command=source.list_command,
                port=source.ssh_port,
                key=source.ssh_key,
            )
        except ssh.SshError as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)

        reg.update(
            source.id,
            last_check=utc_now_iso(),
            last_check_ok=listing.ok,
            last_check_error=None if listing.ok else (listing.stderr or f"exit {listing.code}"),
        )
        if not listing.ok:
            reg.save()
            return JSONResponse(
                {
                    "error": (
                        f"could not list {remote_dir} on {source.ssh_host}. This is a "
                        f"statement about the connection, not about the recorder — the "
                        f"node may be recording perfectly."
                    ),
                    "detail": listing.as_dict(),
                },
                status_code=502,
            )

        today = now().strftime("%Y-%m-%d")
        held = {path.name for path in paths["archive"].glob("*.jsonl")}
        wanted = [
            name
            for name in names
            if name not in held and today not in name and name.endswith(".jsonl")
        ]
        skipped_today = [name for name in names if today in name]

        stage = paths["staging"] / source.id
        stage.mkdir(parents=True, exist_ok=True)

        transferred: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        if not body.dry_run:
            for name in wanted:
                result = ssh.fetch(
                    host=source.ssh_host,
                    remote_path=f"{remote_dir.rstrip('/')}/{name}",
                    local_path=stage / name,
                    port=source.ssh_port,
                    key=source.ssh_key,
                )
                if result.ok:
                    transferred.append({"name": name, "bytes": (stage / name).stat().st_size})
                else:
                    # Staging is the whole point: a partial file dies here.
                    (stage / name).unlink(missing_ok=True)
                    failed.append({"name": name, "detail": result.as_dict()})

        report = staging.merge(stage, paths["archive"], dry_run=body.dry_run)
        if report["merged"]:
            reg.update(
                source.id,
                last_seen=utc_now_iso(),
                last_import=utc_now_iso(),
                last_import_dates=report["dates"],
            )
            _clear_merged(stage, report)
        reg.save()

        return JSONResponse(
            {
                "source_id": source.id,
                "remote_dir": remote_dir,
                "remote_files": len(names),
                "already_held": len(names) - len(wanted) - len(skipped_today),
                "skipped_today": skipped_today,
                "transferred": transferred,
                "failed": failed,
                "merge": report,
            }
        )

    @app.post("/api/import/inbox")
    def inbox(body: InboxRequest) -> JSONResponse:
        """Merge whatever a person has dropped into the inbox.

        The inbox is how a standalone node is collected: a USB stick, a network
        share, a download folder. Files are moved into staging first rather than
        merged in place, so a half-copied file that is still growing is caught by
        the parse check instead of being read as a short day.
        """
        source_inbox = paths["inbox"]
        if not source_inbox.is_dir():
            return JSONResponse(
                {
                    "error": (
                        f"the inbox {source_inbox} does not exist. Create it and drop whole "
                        f"archive files into it — anything except the node's file for today, "
                        f"which is still being written to."
                    )
                },
                status_code=404,
            )
        stage = paths["staging"] / "inbox"
        stage.mkdir(parents=True, exist_ok=True)
        moved: list[str] = []
        for path in sorted(source_inbox.glob("*.jsonl")):
            if not path.is_file():
                continue
            target = stage / path.name
            if target.exists():
                continue
            try:
                shutil.copy2(path, target)
            except OSError:
                continue
            moved.append(path.name)

        report = staging.merge(stage, paths["archive"], dry_run=body.dry_run)
        reg = registry()
        if report["merged"]:
            for source_id in report["sources"]:
                if reg.get(source_id) is None:
                    # A node nobody registered has turned up in the inbox. It is
                    # recorded rather than rejected: the data is real and already
                    # verified, and an unregistered source silently absent from
                    # the coverage grid is worse than one that appears in it.
                    reg.add(
                        id=source_id,
                        kind=KIND_STANDALONE,
                        note="discovered in the inbox; registered automatically",
                    )
                reg.update(
                    source_id,
                    last_import=utc_now_iso(),
                    last_seen=utc_now_iso(),
                    last_import_dates=report["dates"],
                )
            reg.save()
            _clear_merged(stage, report)
            _clear_inbox(source_inbox, report)

        return JSONResponse(
            {"inbox": source_inbox.as_posix(), "copied": moved, "merge": report}
        )

    # -- CREATE NODE -------------------------------------------------------- #

    @app.post("/api/nodes")
    def create_node(body: CreateNodeRequest) -> JSONResponse:
        reg = registry()
        try:
            source_id = sanitise_source_id(body.source_id)
        except RegistryError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if body.kind not in (KIND_SERVER, KIND_STANDALONE):
            return JSONResponse(
                {"error": f"a node is a server or a standalone, not {body.kind!r}"},
                status_code=400,
            )

        public_key: str | None = None
        key_path: Path | None = None
        if body.kind == KIND_SERVER:
            candidates = [Path(body.ssh_key + ".pub")] if body.ssh_key else []
            candidates += list(KEY_CANDIDATES)
            public_key, key_path = node_package.find_public_key(candidates)
            if public_key is None:
                return JSONResponse(
                    {
                        "error": (
                            "no SSH public key was found, so a server node cannot be "
                            "authorised. Generate one on THIS machine with:\n"
                            "    ssh-keygen -t ed25519 -f ~/.ssh/acsoe_node -C acsoe-master\n"
                            "The private half stays here and is never copied into a "
                            "package; only the .pub goes to the node."
                        )
                    },
                    status_code=400,
                )

        out_dir = paths["nodes"] / source_id
        try:
            built = node_package.build(
                repo_root=paths["repo"],
                out_dir=out_dir,
                source_id=source_id,
                kind=body.kind,
                archive_dir=body.archive_dir,
                public_key=public_key,
            )
        except node_package.PackagingError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)

        entry: dict[str, Any] = {"id": source_id, "kind": body.kind}
        if body.kind == KIND_SERVER:
            entry.update(
                ssh_host=body.ssh_host,
                ssh_port=body.ssh_port,
                ssh_key=(str(key_path)[:-4] if key_path else body.ssh_key),
                archive_dir=body.remote_archive_dir or body.archive_dir,
            )
        else:
            entry.update(archive_dir=body.archive_dir)
        try:
            reg.add(**entry)
            reg.save()
        except RegistryError as exc:
            return JSONResponse(
                {"error": str(exc), "package": built, "registered": False}, status_code=409
            )

        built["registered"] = True
        built["public_key_from"] = str(key_path) if key_path else None
        return JSONResponse(built, status_code=201)

    return app


# --------------------------------------------------------------------------- #
# Helpers the routes share
# --------------------------------------------------------------------------- #


def _source_payload(
    source: Source,
    reg: Registry,
    *,
    paths: dict[str, Path],
    now: datetime,
    check: bool,
) -> dict[str, Any]:
    """One source, with the quality of the knowledge attached to it.

    `liveness` is one of four values and never a boolean:

    * `live`       — read just now, from local disk
    * `as_of`      — read over SSH at a stated time
    * `unreachable`— we tried and could not; a statement about the network
    * `none`       — there is no way to know, and none is claimed
    """
    base: dict[str, Any] = {
        "id": source.id,
        "kind": source.kind,
        "note": source.note,
        "archive_dir": source.archive_dir,
        "last_seen": source.last_seen,
        "last_import": source.last_import,
        "last_import_dates": source.last_import_dates,
    }

    if source.kind == KIND_MASTER:
        status = local_status(Path(source.archive_dir or paths["archive"]), now=now)
        liveness, detail = master_liveness(status)
        base.update(
            liveness=liveness,
            detail=detail,
            status=status,
            checked_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        return base

    if source.kind == KIND_STANDALONE:
        # The whole rule, in one place. There is no route to this machine, so
        # there is nothing to check and nothing is claimed. What IS known is when
        # somebody last carried data over, and what that data covered.
        base.update(
            liveness="none",
            detail=(
                "no live status: this node has no route to or from the master. "
                "It may be recording perfectly. Silence is not evidence."
            ),
            checked_at=None,
            status={
                "last_import": source.last_import,
                "last_import_dates": source.last_import_dates,
            },
        )
        return base

    # A server node.
    if check and source.ssh_host:
        result = ssh.check(
            host=source.ssh_host,
            port=source.ssh_port,
            key=source.ssh_key,
            archive_dir=source.archive_dir,
        )
        ok = result.ok and "missing-archive" not in result.stdout
        reg.update(
            source.id,
            last_check=utc_now_iso(),
            last_check_ok=ok,
            last_check_error=None if ok else (result.stderr.strip() or result.stdout.strip()),
            **({"last_seen": utc_now_iso()} if ok else {}),
        )
        source = reg.require(source.id)

    if source.last_check is None:
        base.update(
            liveness="none",
            detail=(
                "never checked. Press Check now to reach out over SSH — it is not done "
                "on a page load because it takes seconds per node."
            ),
            checked_at=None,
        )
    elif source.last_check_ok:
        base.update(
            liveness="as_of",
            detail="reachable, and its archive directory is where the registry says",
            checked_at=source.last_check,
        )
    else:
        base.update(
            liveness="unreachable",
            detail=(
                f"could not be reached: {source.last_check_error or 'no detail recorded'}. "
                f"This says the connection failed. It does not say the node stopped "
                f"recording, and it must not be read that way."
            ),
            checked_at=source.last_check,
        )
    base["ssh_host"] = source.ssh_host
    base["ssh_port"] = source.ssh_port
    return base


def _clear_merged(stage: Path, report: dict[str, Any]) -> None:
    """Remove the staged copies of files that reached the archive.

    Only the ones that merged. A refused file is left in staging on purpose: it is
    evidence, somebody has to look at it, and deleting it would destroy the only
    copy of whatever arrived broken.
    """
    for item in report.get("files", []):
        if item.get("state") != "merged":
            continue
        candidate = stage / str(item.get("name"))
        if candidate.is_file():
            candidate.unlink(missing_ok=True)


def _clear_inbox(inbox: Path, report: dict[str, Any]) -> None:
    """Move merged files out of the inbox into a `done` folder beside it.

    Moved, not deleted. The inbox is fed by a person carrying a disk, and the
    master's archive is not yet backed up anywhere — deleting their only other
    copy the moment it verifies is a policy for somebody with backups.
    """
    done = inbox / "done"
    for item in report.get("files", []):
        if item.get("state") != "merged":
            continue
        candidate = inbox / str(item.get("name"))
        if not candidate.is_file():
            continue
        done.mkdir(parents=True, exist_ok=True)
        target = done / candidate.name
        if target.exists():
            continue
        try:
            candidate.replace(target)
        except OSError:
            continue
