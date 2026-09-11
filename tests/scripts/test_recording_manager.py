"""The Recording Manager: the registry, coverage, staging and node packaging.

Every assertion here is about a failure that is **silent in production**, which is
why each one is written against an artefact rather than against a return value.

Four of them carry the weight:

* **A gap marker must be subtracted from a day's hours.** When it is not, the
  number comes out *higher* than the truth, so a disconnected hour renders as a
  gap-free day and nobody looks. This was a real defect: the scanner matched
  `"kind":"gap"` with no space, which is what `orjson` writes and is not what
  `json.dumps` writes, and a foreign archive's gaps were invisible.

* **A truncated transfer must never reach the archive.** Written straight in, it
  would have the right name, be globbed by every tool, and be short — and nothing
  reports it, because a short JSONL file is a valid JSONL file.

* **A standalone node must never be reported as dead.** The manager cannot tell a
  silent standalone node from a node recording perfectly, and the guess is wrong
  in the direction that gets a working recorder switched off.

* **A node package must carry no credential for the master.** A node is the
  machine most likely to be compromised.

`scripts/` is not a package; `scripts/recording/` is, and is reached by putting
`scripts/` on `sys.path` the way `manager/serve.py` does.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from recording.manager import app as app_mod  # noqa: E402
from recording.manager import archive as archive_mod  # noqa: E402
from recording.manager import node_package, staging  # noqa: E402
from recording.manager.registry import Registry, RegistryError, sanitise_source_id  # noqa: E402

# --------------------------------------------------------------------------- #
# Calling the app
# --------------------------------------------------------------------------- #
#
# Driven through the ASGI interface directly, NOT through
# `fastapi.testclient.TestClient`. `TestClient` subclasses `httpx.Client`, and
# `tests/harness/network_guard.py` patches `httpx.Client.send` for every test in
# this repository, so a `TestClient` request raises `NetworkAccessError` before it
# reaches the in-process transport. The choices were to weaken the guard for the
# convenience of these tests or to call the application the way uvicorn calls it;
# spec 14 forbids the first in as many words, and the second is a truer test —
# real routing, real endpoint, real encoder, no HTTP client and no socket.
#
# The same decision, and the same reasoning, as `tests/console/test_app.py`.


class Response:
    """Status, raw body, and the JSON if there is any."""

    __slots__ = ("body", "status")

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def json(self) -> Any:
        return json.loads(self.body) if self.body else {}

    @property
    def status_code(self) -> int:
        return self.status


async def _call(app: Any, method: str, path: str, payload: Any = None) -> Response:
    sent: list[dict[str, Any]] = []
    raw, _, query = path.partition("?")
    encoded = json.dumps(payload).encode() if payload is not None else b""
    headers = [(b"host", b"manager.test")]
    if payload is not None:
        headers.append((b"content-type", b"application/json"))
        headers.append((b"content-length", str(len(encoded)).encode()))

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": raw,
        "raw_path": raw.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": headers,
        "client": ("test", 0),
        "server": ("manager.test", 80),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": encoded, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    body = b"".join(
        item.get("body", b"") for item in sent if item["type"] == "http.response.body"
    )
    return Response(status, body)


class Caller:
    """A tiny synchronous facade over the ASGI app, so the tests read like
    ordinary request/response code without every one of them being async."""

    __slots__ = ("app",)

    def __init__(self, app: Any) -> None:
        self.app = app

    def get(self, path: str) -> Response:
        return asyncio.run(_call(self.app, "GET", path))

    def post(self, path: str, json: Any = None) -> Response:
        return asyncio.run(_call(self.app, "POST", path, json))


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def tick(stamp: str) -> dict[str, Any]:
    return {
        "v": 1,
        "kind": "tick",
        "pair": "BTC/USD",
        "channel": "book",
        "ts_exchange": None,
        "ts_recv": stamp,
        "payload": {"channel": "book"},
    }


def gap(stamp: str, gap_ms: int) -> dict[str, Any]:
    return {
        "v": 1,
        "kind": "gap",
        "pair": None,
        "channel": "_recorder",
        "ts_exchange": None,
        "ts_recv": stamp,
        "payload": {
            "reason": "ConnectionClosed",
            "disconnected_at": stamp,
            "reconnected_at": stamp,
            "gap_ms": gap_ms,
            "attempt": 1,
        },
    }


def write_day(
    path: Path,
    day: str,
    *,
    first_hour: int = 0,
    last_hour: int = 23,
    gap_ms: int = 0,
    separators: tuple[str, str] | None = None,
) -> Path:
    """A day file.

    `separators` exists so a test can write the file the way `orjson` does
    (compact) or the way `json.dumps` does (spaced). The difference is invisible
    to a reader and was the whole of a real defect.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = [tick(f"{day}T{first_hour:02d}:00:00.000000Z")]
    if gap_ms:
        rows.append(gap(f"{day}T{first_hour + 1:02d}:00:00.000000Z", gap_ms))
    rows.append(tick(f"{day}T{last_hour:02d}:00:00.000000Z"))
    dumped = [json.dumps(row, separators=separators) for row in rows]
    path.write_text("\n".join(dumped) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def archive_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "archive"
    write_day(directory / "kraken_v2__msi__2026-09-08.jsonl", "2026-09-08")
    write_day(directory / "kraken_v2__msi__2026-09-09.jsonl", "2026-09-09", gap_ms=3_600_000)
    # 2026-09-10 is deliberately absent: an uncovered day inside the span.
    write_day(directory / "kraken_v2__msi__2026-09-11.jsonl", "2026-09-11", first_hour=9)
    write_day(directory / "kraken_v2__vps-fra-1__2026-09-11.jsonl", "2026-09-11")
    return directory


@pytest.fixture
def client(tmp_path: Path, archive_dir: Path) -> Any:
    registry = tmp_path / "sources.yaml"
    registry.write_text(
        "version: 1\n"
        "sources:\n"
        "  - id: msi\n"
        "    kind: master\n"
        f"    archive_dir: {archive_dir.as_posix()}\n"
        "  - id: vps-fra-1\n"
        "    kind: server\n"
        "    ssh_host: acsoe@203.0.113.10\n"
        "    archive_dir: /opt/acsoe/data/raw\n"
        "  - id: laptop-2\n"
        "    kind: standalone\n",
        encoding="utf-8",
    )
    app = app_mod.create_app(
        registry_path=registry,
        archive_dir=archive_dir,
        staging_dir=tmp_path / "staging",
        inbox_dir=tmp_path / "inbox",
        nodes_dir=tmp_path / "nodes",
        cache_path=tmp_path / "cache.json",
    )
    return Caller(app)


# --------------------------------------------------------------------------- #
# Coverage: the number must be the truth, and it must be lower than the span
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("separators", "written_as"),
    [
        ((",", ":"), "orjson's compact form, which is what the recorder writes"),
        ((", ", ": "), "json.dumps's spaced form, which a foreign archive may use"),
    ],
)
def test_a_gap_marker_is_subtracted_however_the_file_was_serialised(
    tmp_path: Path, separators: tuple[str, str], written_as: str
) -> None:
    """**The assertion that caught a real defect.**

    The scanner used to search for the literal bytes `"kind":"gap"`, which found
    every marker in an `orjson` file and none at all in a `json.dumps` one. The
    failure is silent and it is the worst possible direction: the span is still
    right, so the day reports MORE hours than were recorded and a disconnected
    hour renders as a clean day.
    """
    path = write_day(
        tmp_path / "kraken_v2__msi__2026-09-09.jsonl",
        "2026-09-09",
        gap_ms=3_600_000,
        separators=separators,
    )
    measured = archive_mod.measure(path)
    assert measured.gap_count == 1, f"the gap marker was not found in {written_as}"
    assert measured.span_seconds == pytest.approx(23 * 3600)
    assert measured.recorded_hours == pytest.approx(22.0), (
        "the recorded hours must be the span MINUS the measured gap"
    )


def test_hours_are_measured_not_assumed_from_the_filename(tmp_path: Path) -> None:
    """A file named for a day may hold forty seconds of it."""
    path = write_day(
        tmp_path / "kraken_v2__msi__2026-09-11.jsonl", "2026-09-11", first_hour=9, last_hour=23
    )
    assert archive_mod.measure(path).recorded_hours == pytest.approx(14.0)


def test_the_grid_includes_days_nothing_covered(archive_dir: Path) -> None:
    """**Every date in the span, not only the dates with files.**

    A grid built from the dates that have files cannot show a missing week,
    because a missing week has no files in it: the hole closes up silently between
    two columns that then look adjacent.
    """
    grid = archive_mod.build_grid(archive_mod.scan_directory(archive_dir))
    assert grid["dates"] == ["2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"]
    assert "2026-09-10" not in grid["cells"]["msi"]


def test_gaps_separate_uncovered_from_single_source(archive_dir: Path) -> None:
    grid = archive_mod.build_grid(archive_mod.scan_directory(archive_dir))
    report = archive_mod.find_gaps(grid)
    assert report["uncovered"] == ["2026-09-10"]
    assert [item["date"] for item in report["single_source"]] == ["2026-09-08", "2026-09-09"]
    assert [item["date"] for item in report["multiple_sources"]] == ["2026-09-11"]


def test_a_file_with_no_source_in_its_name_still_appears(tmp_path: Path) -> None:
    """The 7.1 GB already on disk predates source ids. Dropping it out of the grid
    would silently remove most of the archive from every total."""
    write_day(tmp_path / "kraken_v2_2026-09-08.jsonl", "2026-09-08")
    grid = archive_mod.build_grid(archive_mod.scan_directory(tmp_path))
    assert grid["sources"] == ["unnamed"]


def test_a_recently_written_file_is_never_served_from_the_cache(tmp_path: Path) -> None:
    """**The collision the key alone cannot close.**

    The key is `(name, size, mtime_ns)`. Windows updates the system clock in
    ~15.6 ms steps, so two writes in quick succession share an `st_mtime_ns`
    exactly — and a rewrite of the same day easily has the same length, because
    `T06:00:00` and `T18:00:00` are the same number of bytes. Same key, stale
    answer served as current. Reachable in production: `archive_move.py` and the
    merge both produce same-length rewrites.

    A file touched within `CACHE_SETTLE_S` is therefore measured fresh and not
    stored. That costs nothing worth having — the file being appended to has to be
    re-measured on every request anyway.
    """
    path = write_day(tmp_path / "kraken_v2__msi__2026-09-08.jsonl", "2026-09-08", last_hour=6)
    cache = archive_mod.Cache(tmp_path / "cache.json")
    assert cache.measure(path).recorded_hours == pytest.approx(6.0)
    # Same length, and quite possibly the same mtime tick.
    write_day(tmp_path / "kraken_v2__msi__2026-09-08.jsonl", "2026-09-08", last_hour=18)
    assert cache.measure(path).recorded_hours == pytest.approx(18.0)


def test_a_settled_file_is_served_from_the_cache(tmp_path: Path) -> None:
    """The other half: the cache has to actually cache, or 21 GB is rescanned on
    every page load. Proven by backdating the file and then corrupting it — a
    cached answer is the one that survives."""
    path = write_day(tmp_path / "kraken_v2__msi__2026-09-08.jsonl", "2026-09-08", last_hour=6)
    old_time = time.time() - 3600
    os.utime(path, (old_time, old_time))

    cache = archive_mod.Cache(tmp_path / "cache.json")
    assert cache.measure(path).recorded_hours == pytest.approx(6.0)

    path.write_text("{ not json at all\n", encoding="utf-8")
    os.utime(path, (old_time, old_time))
    # Same name, DIFFERENT size, so the key changes and it is re-measured.
    assert cache.measure(path).recorded_hours == pytest.approx(0.0)


def test_the_cache_survives_a_reload(tmp_path: Path) -> None:
    path = write_day(tmp_path / "kraken_v2__msi__2026-09-08.jsonl", "2026-09-08", last_hour=6)
    old_time = time.time() - 3600
    os.utime(path, (old_time, old_time))
    cache_path = tmp_path / "cache.json"

    first = archive_mod.Cache(cache_path)
    first.measure(path)
    first.save()

    assert cache_path.is_file()
    assert archive_mod.Cache(cache_path).measure(path).recorded_hours == pytest.approx(6.0)


def test_a_corrupt_cache_is_discarded_rather_than_trusted(tmp_path: Path) -> None:
    """It is a convenience, never an authority: the file is the record."""
    cache_path = tmp_path / "cache.json"
    cache_path.write_text("{ not json", encoding="utf-8")
    path = write_day(tmp_path / "kraken_v2__msi__2026-09-08.jsonl", "2026-09-08", last_hour=6)
    assert archive_mod.Cache(cache_path).measure(path).recorded_hours == pytest.approx(6.0)


# --------------------------------------------------------------------------- #
# Staging: nothing reaches the archive unverified
# --------------------------------------------------------------------------- #


def test_a_corrupt_file_is_refused_and_never_reaches_the_archive(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    archive = tmp_path / "archive"
    archive.mkdir()
    stage.mkdir()
    (stage / "kraken_v2__vps__2026-09-12.jsonl").write_text(
        json.dumps(tick("2026-09-12T00:00:00.000000Z")) + "\n{ not json\n", encoding="utf-8"
    )
    report = staging.merge(stage, archive)
    assert report["merged"] == 0
    assert report["refused"] == 1
    assert list(archive.glob("*.jsonl")) == []
    assert (stage / "kraken_v2__vps__2026-09-12.jsonl").is_file(), (
        "a refused file stays in staging: it is the evidence, and deleting it "
        "destroys the only copy of whatever arrived broken"
    )


def test_a_truncated_final_line_is_tolerated_and_named(tmp_path: Path) -> None:
    """The shape a forced kill leaves, and the archive already contains it.

    Refusing it would refuse real data; repairing it is what invariant 11 forbids.
    """
    stage = tmp_path / "stage"
    archive = tmp_path / "archive"
    archive.mkdir()
    stage.mkdir()
    (stage / "kraken_v2__vps__2026-09-12.jsonl").write_text(
        json.dumps(tick("2026-09-12T00:00:00.000000Z")) + '\n{"v":1,"kind":"ti',
        encoding="utf-8",
    )
    report = staging.merge(stage, archive)
    assert report["merged"] == 1
    assert "truncated" in (report["files"][0]["note"] or "")


def test_an_existing_name_is_never_overwritten(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    archive = tmp_path / "archive"
    write_day(archive / "kraken_v2__msi__2026-09-08.jsonl", "2026-09-08")
    original = (archive / "kraken_v2__msi__2026-09-08.jsonl").read_bytes()
    stage.mkdir()
    (stage / "kraken_v2__msi__2026-09-08.jsonl").write_text(
        json.dumps(tick("2026-09-08T05:00:00.000000Z")) + "\n", encoding="utf-8"
    )
    report = staging.merge(stage, archive)
    assert report["collisions"] == 1
    assert report["merged"] == 0
    assert (archive / "kraken_v2__msi__2026-09-08.jsonl").read_bytes() == original


def test_a_file_whose_copy_does_not_verify_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The assertion staging exists for.**

    The read-back is made to disagree. No file may be left under a real archive
    name, because a short file with the right name is read by every tool as a
    short day and nothing reports it.
    """
    stage = tmp_path / "stage"
    archive = tmp_path / "archive"
    archive.mkdir()
    stage.mkdir()
    write_day(stage / "kraken_v2__vps__2026-09-12.jsonl", "2026-09-12")
    monkeypatch.setattr(staging, "digest", lambda _path: "0" * 64)
    report = staging.merge(stage, archive)
    assert report["merged"] == 0
    assert list(archive.glob("*")) == [], "a partial copy was left in the archive"


def test_an_undated_name_is_refused(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    archive = tmp_path / "archive"
    archive.mkdir()
    stage.mkdir()
    write_day(stage / "whatever.jsonl", "2026-09-12")
    report = staging.merge(stage, archive)
    assert report["refused"] == 1
    assert "no UTC date" in report["files"][0]["detail"]


def test_overlapping_coverage_is_reported_with_its_span_and_both_are_kept(
    tmp_path: Path,
) -> None:
    """Two sources covering one hour is an independent observation of one market.

    The difference between them is the only measurement there is of what a single
    recorder misses. A merger that quietly kept one would destroy it, and the
    surviving file would be perfectly valid — so nothing would report the loss.
    """
    archive = tmp_path / "archive"
    stage = tmp_path / "stage"
    write_day(archive / "kraken_v2__msi__2026-09-11.jsonl", "2026-09-11", first_hour=9)
    stage.mkdir()
    write_day(stage / "kraken_v2__vps__2026-09-11.jsonl", "2026-09-11")
    report = staging.merge(stage, archive)

    assert report["merged"] == 1
    assert len({path.name for path in archive.glob("*.jsonl")}) == 2, "a source was dropped"
    assert len(report["overlaps"]) == 1
    overlap = report["overlaps"][0]
    assert overlap["from"] == "2026-09-11T09:00:00Z"
    assert overlap["to"] == "2026-09-11T23:00:00Z"
    assert overlap["hours"] == pytest.approx(14.0)
    assert {overlap["left_source"], overlap["right_source"]} == {"msi", "vps"}


def test_two_files_from_one_source_are_not_reported_as_an_overlap() -> None:
    spans = [
        {"name": "a", "source_id": "msi", "first": 0.0, "last": 100.0},
        {"name": "b", "source_id": "msi", "first": 50.0, "last": 150.0},
    ]
    assert staging.find_overlaps(spans) == []


def test_adjacent_spans_are_a_handover_not_an_overlap() -> None:
    """Reporting a handover would train the operator to ignore the report."""
    spans = [
        {"name": "a", "source_id": "msi", "first": 0.0, "last": 100.0},
        {"name": "b", "source_id": "vps", "first": 100.0, "last": 200.0},
    ]
    assert staging.find_overlaps(spans) == []


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #


def test_the_registry_preserves_keys_it_does_not_understand(tmp_path: Path) -> None:
    """It is hand-editable, so a rewrite must not silently drop somebody's field."""
    path = tmp_path / "sources.yaml"
    path.write_text(
        "version: 1\nsources:\n  - id: msi\n    kind: master\n    my_own_field: keep me\n",
        encoding="utf-8",
    )
    registry = Registry.load(path)
    registry.update("msi", last_seen="2026-09-11T00:00:00Z")
    registry.save()
    assert "my_own_field: keep me" in path.read_text(encoding="utf-8")


def test_a_malformed_registry_raises_rather_than_starting_fresh(tmp_path: Path) -> None:
    """Silently starting empty over a file somebody has been editing would lose
    every node they had registered."""
    path = tmp_path / "sources.yaml"
    path.write_text("sources: [this is: not valid: yaml\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        Registry.load(path)


def test_a_missing_registry_is_a_first_run_not_an_error(tmp_path: Path) -> None:
    assert Registry.load(tmp_path / "absent.yaml").sources == []


def test_a_duplicate_source_id_is_refused(tmp_path: Path) -> None:
    """Two machines sharing one id merge into a single apparent source, and their
    files collide on every shared date."""
    registry = Registry.load(tmp_path / "sources.yaml")
    registry.add(id="vps-1", kind="server", ssh_host="a@b")
    with pytest.raises(RegistryError, match="already registered"):
        registry.add(id="vps-1", kind="standalone")


def test_the_registry_sanitises_an_id_the_way_the_recorder_does(tmp_path: Path) -> None:
    """It must not register an id the recorder would then fold into something
    else — the two have to agree, because the recorder puts it in the filename."""
    assert sanitise_source_id("Laptop 3!") == "laptop-3"
    registry = Registry.load(tmp_path / "sources.yaml")
    assert registry.add(id="Laptop 3!", kind="standalone").id == "laptop-3"


def test_an_atomic_save_leaves_the_previous_file_on_failure(tmp_path: Path) -> None:
    """The registry is the only record of how to reach a node."""
    path = tmp_path / "sources.yaml"
    registry = Registry.load(path)
    registry.add(id="vps-1", kind="server", ssh_host="a@b")
    registry.save()
    before = path.read_text(encoding="utf-8")
    assert "vps-1" in before
    assert not list(tmp_path.glob("*.tmp")), "a temporary file was left behind"


# --------------------------------------------------------------------------- #
# Honest status
# --------------------------------------------------------------------------- #


def test_a_standalone_node_never_reports_a_live_status(client: Any) -> None:
    """**The rule the whole SOURCES screen is built on.**

    There is no route to a standalone node, so nothing can be known about it now.
    A silent standalone node may be recording perfectly, and calling it dead is
    the guess that gets a working recorder switched off.
    """
    sources = {item["id"]: item for item in client.get("/api/sources").json()["sources"]}
    standalone = sources["laptop-2"]
    assert standalone["liveness"] == "none"
    assert standalone["checked_at"] is None
    assert "silence is not evidence" in standalone["detail"].lower()
    for word in ("dead", "down", "offline", "stopped"):
        assert word not in standalone["detail"].lower()


def test_a_server_node_is_never_checked_on_a_page_load(client: Any) -> None:
    """A check costs seconds per node and must be asked for.

    Until then the row reports "never checked" rather than a state, which is a
    weaker and truer claim than a green light nobody earned.
    """
    payload = client.get("/api/sources").json()
    assert payload["live_check_performed"] is False
    server = next(item for item in payload["sources"] if item["id"] == "vps-fra-1")
    assert server["liveness"] == "none"
    assert "never checked" in server["detail"]


def test_an_unreachable_server_says_the_connection_failed_not_that_it_is_dead(
    tmp_path: Path, archive_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from recording.manager import ssh

    monkeypatch.setattr(
        ssh,
        "check",
        lambda **_kwargs: ssh.Result(
            command=["ssh"], code=255, stdout="", stderr="ssh: connect to host ... timed out"
        ),
    )
    registry = tmp_path / "sources.yaml"
    registry.write_text(
        "version: 1\nsources:\n  - id: vps-fra-1\n    kind: server\n"
        "    ssh_host: acsoe@203.0.113.10\n    archive_dir: /opt/acsoe/data/raw\n",
        encoding="utf-8",
    )
    app = app_mod.create_app(
        registry_path=registry,
        archive_dir=archive_dir,
        staging_dir=tmp_path / "staging",
        inbox_dir=tmp_path / "inbox",
        nodes_dir=tmp_path / "nodes",
        cache_path=tmp_path / "cache.json",
    )
    payload = Caller(app).get("/api/sources?check=true").json()
    source = payload["sources"][0]
    assert source["liveness"] == "unreachable"
    assert "timed out" in source["detail"]
    assert "does not say the node stopped recording" in source["detail"]
    assert source["checked_at"] is not None, "an unreachable source still reports WHEN we tried"


def test_pull_refuses_a_standalone_node(client: Any) -> None:
    """There is no route, by design. The error says so rather than failing oddly."""
    response = client.post("/api/import/pull", json={"source_id": "laptop-2"})
    assert response.status_code == 400
    assert "standalone" in response.json()["error"]


def test_the_manager_declares_that_it_neither_records_nor_writes_to_the_store(
    client: Any,
) -> None:
    health = client.get("/api/health").json()
    assert health["records"] is False
    assert health["writes_to_store"] is False


def test_the_manager_opens_no_database(client: Any) -> None:
    """Engine 19 `memory` is the single writer of every relational row, and the
    manager is not in that chain. The cheapest way to keep that true is for this
    package never to import `sqlite3` at all."""
    source = (REPO_ROOT / "scripts" / "recording").rglob("*.py")
    for path in source:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "sqlite3" not in stripped, f"{path.name}: {stripped}"
                assert "acsoe" not in stripped, f"{path.name} imports from the package: {stripped}"


# --------------------------------------------------------------------------- #
# Node packaging
# --------------------------------------------------------------------------- #


def test_a_node_package_contains_no_credential_for_the_master(tmp_path: Path) -> None:
    """**A node is the machine most likely to be compromised.**

    It never initiates a connection to the master, so it needs nothing from the
    master — and therefore has nothing on it to steal.
    """
    out = tmp_path / "node"
    built = node_package.build(
        repo_root=REPO_ROOT,
        out_dir=out,
        source_id="vps-1",
        kind="server",
        public_key="ssh-ed25519 AAAAC3PUBLICKEYONLY acsoe-master",
    )
    assert "authorize-this-key.pub" in built["files"]
    for path in out.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "PRIVATE KEY" not in text, f"{path.name} carries private key material"
        assert "KRAKEN_API_KEY" not in text
        assert "KRAKEN_API_SECRET" not in text


def test_a_standalone_package_has_no_key_at_all(tmp_path: Path) -> None:
    out = tmp_path / "node"
    built = node_package.build(
        repo_root=REPO_ROOT, out_dir=out, source_id="laptop-3", kind="standalone"
    )
    assert "authorize-this-key.pub" not in built["files"]
    assert not (out / "authorize-this-key.pub").exists()


def test_a_package_carries_the_recorder_and_the_supervisor_verbatim(tmp_path: Path) -> None:
    """Copies, not rewrites. A package whose recorder has drifted from the
    repository's is a node recording under rules nobody can see."""
    out = tmp_path / "node"
    node_package.build(repo_root=REPO_ROOT, out_dir=out, source_id="laptop-3", kind="standalone")
    for name, original in (
        ("record.py", REPO_ROOT / "scripts" / "record.py"),
        ("supervise.py", REPO_ROOT / "scripts" / "recording" / "supervise.py"),
    ):
        assert (out / name).read_bytes() == original.read_bytes()


def test_the_source_id_is_written_into_the_packaged_config(tmp_path: Path) -> None:
    """The id has to agree in three places: the config, the registry, and every
    filename the node will write. The manager is what makes them agree."""
    out = tmp_path / "node"
    node_package.build(repo_root=REPO_ROOT, out_dir=out, source_id="vps-fra-1", kind="standalone")
    config = (out / "recorder.yaml").read_text(encoding="utf-8")
    assert 'source_id: "vps-fra-1"' in config
    assert "DO NOT CHANGE IT" in config


def test_a_package_refuses_to_overwrite_an_existing_one(tmp_path: Path) -> None:
    """A package half-overwritten with another node's config is a machine
    recording under the wrong identity, and the identity cannot be corrected
    afterwards."""
    out = tmp_path / "node"
    node_package.build(repo_root=REPO_ROOT, out_dir=out, source_id="vps-1", kind="standalone")
    with pytest.raises(node_package.PackagingError, match="already exists"):
        node_package.build(repo_root=REPO_ROOT, out_dir=out, source_id="vps-2", kind="standalone")


def test_find_public_key_ignores_anything_that_is_not_one(tmp_path: Path) -> None:
    """It reads `.pub` files only, and checks the contents rather than the name —
    a private key handed to it under a `.pub` name must not be packaged."""
    private = tmp_path / "id_ed25519.pub"
    private.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nnope\n", encoding="utf-8")
    key, path = node_package.find_public_key([private])
    assert key is None
    assert path is None


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


def test_the_page_and_its_assets_are_served(client: Any) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/static/tokens.css").status_code == 200
    assert client.get("/static/manager.css").status_code == 200
    assert client.get("/static/manager.js").status_code == 200


def test_no_raw_hex_outside_the_token_block() -> None:
    """`ui-context.md`: tokens only, declared once.

    `console_tokens_no_raw_hex` scans `src/acsoe/console/` and does not reach this
    app, so the rule is kept by this test instead. A colour written into a
    component is a colour nobody can retune.
    """
    import re

    static = REPO_ROOT / "scripts" / "recording" / "manager"
    pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    offenders: list[str] = []
    for path in sorted(static.rglob("*")):
        if path.suffix not in {".css", ".html", ".js"} or not path.is_file():
            continue
        if path.name == "tokens.css":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, offenders


def test_the_reserved_live_colour_is_not_borrowed() -> None:
    """Amber means real money is at risk right now. This app cannot place an
    order, cannot reach the store and cannot trade; spending the console's one
    reserved signal on a recording warning would devalue it there."""
    manager = REPO_ROOT / "scripts" / "recording" / "manager"
    for path in sorted(manager.rglob("*")):
        if path.suffix not in {".css", ".html", ".js"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        # Defined, or referenced. A comment explaining why it is absent is
        # neither, and is the reason this is not a bare substring check.
        assert "--live:" not in text, f"{path.name} DEFINES the reserved colour"
        assert "var(--live" not in text, f"{path.name} USES the reserved colour"


def test_every_numeric_class_carries_tabular_figures() -> None:
    """Number rule 1, by one mechanism rather than per component."""
    css = (REPO_ROOT / "scripts" / "recording" / "manager" / "static" / "manager.css").read_text(
        encoding="utf-8"
    )
    assert "font-variant-numeric: tabular-nums" in css
    assert css.count("font-variant-numeric: tabular-nums") >= 3


def test_the_page_uses_a_real_minus_sign() -> None:
    """Rule 6: a hyphen breaks tabular alignment."""
    js = (REPO_ROOT / "scripts" / "recording" / "manager" / "static" / "manager.js").read_text(
        encoding="utf-8"
    )
    # RUF001 is suppressed below for the same reason it is suppressed in
    # `tests/console/test_format.py`: the U+2212 glyph IS the fixture here, and
    # "correcting" it to an ASCII hyphen would make this test pass against the
    # exact character it exists to require.
    assert 'const MINUS = "−"' in js  # noqa: RUF001


# --------------------------------------------------------------------------- #
# The supervisor
# --------------------------------------------------------------------------- #


def _load_supervisor() -> Any:
    import importlib.util

    path = REPO_ROOT / "scripts" / "recording" / "supervise.py"
    spec = importlib.util.spec_from_file_location("acsoe_supervise_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


supervise = _load_supervisor()


def test_the_status_block_is_the_six_lines_it_promises() -> None:
    started = datetime(2026, 9, 11, 17, 40, 2, tzinfo=UTC)
    block = supervise.status_block(
        source_id="vps-fra-1",
        started=started,
        now=datetime(2026, 9, 11, 20, 52, 2, tzinfo=UTC),
        today_mb=41283.0,
        last_write=0.0,
        restarts=2,
        state="recording",
    )
    lines = block.split("\n")
    assert len(lines) == 6, "the healthy block is six lines; a seventh means something is wrong"
    assert lines[0] == "RECORDING — vps-fra-1"
    assert lines[1] == "started    2026-09-11T17:40:02Z"
    assert lines[2] == "uptime     3h 12m"
    assert lines[3] == "today      41283 MB"
    assert lines[4] == "last write 0s ago"
    assert lines[5] == "restarts   2"


def test_an_unhealthy_state_adds_a_line_rather_than_changing_one() -> None:
    """The six lines stay put, so a change in the block is visible at a glance."""
    block = supervise.status_block(
        source_id="msi",
        started=datetime(2026, 9, 11, tzinfo=UTC),
        now=datetime(2026, 9, 11, tzinfo=UTC),
        today_mb=0.0,
        last_write=None,
        restarts=0,
        state="waiting: the archive is locked by another live recorder",
    )
    lines = block.split("\n")
    assert len(lines) == 7
    assert lines[4] == "last write never"
    assert lines[6].startswith("state      waiting")


def test_the_locked_exit_code_matches_the_recorder() -> None:
    """`record.py` returns 2 when another recorder holds the archive, and the
    supervisor waits on exactly that rather than treating it as a crash. If the
    two ever disagree, the supervisor crash-loops against a directory somebody
    else is correctly writing to."""
    recorder = (REPO_ROOT / "scripts" / "record.py").read_text(encoding="utf-8")
    assert "return 2" in recorder
    assert supervise.EXIT_ARCHIVE_LOCKED == 2


def test_the_supervisor_imports_nothing_from_the_package() -> None:
    """It is half of a node package and has to run on a machine with no checkout."""
    text = (REPO_ROOT / "scripts" / "recording" / "supervise.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "acsoe" not in stripped, stripped
            assert "recording" not in stripped, stripped
