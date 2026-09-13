"""Spec 08 — structured logging, redaction, and directory creation.

The redaction test is the point of this file. Invariant 13 says a secret never
enters the repo and is never logged; ``code-standards.md`` says redaction happens
at the client layer, not the call site. Both are claims about behaviour, so both
are asserted by planting a real secret and reading the real file back.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from acsoe.platform.logging import (
    MIN_SECRET_LENGTH,
    REDACTION,
    bind_cycle,
    bind_run,
    clear_context,
    clear_cycle,
    clear_secrets,
    configure_logging,
    get_logger,
    register_secret,
    registered_secret_count,
    scrub_text,
)
from acsoe.platform.paths import ensure_runtime_directories, runtime_paths

PLANTED_KEY = "kR4k3n-Ap1-K3y-DO-NOT-LOG-9f2c1a7b"
PLANTED_SECRET = "c2VjcmV0LWJhc2U2NC1raW5kLW9mLXRoaW5nLXRoYXQta3Jha2VuLXVzZXM="


@pytest.fixture(autouse=True)
def _isolated_logging(tmp_path: Path) -> Iterator[Path]:
    clear_secrets()
    clear_context()
    log_path = configure_logging(log_dir=tmp_path / "logs", level="DEBUG")
    yield log_path
    logging.shutdown()
    for handler in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(handler)
        handler.close()
    clear_secrets()
    clear_context()
    structlog.reset_defaults()


def _read_lines(log_path: Path) -> list[dict[str, object]]:
    logging.getLogger().handlers[0].flush()
    text = log_path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --------------------------------------------------------------------------
# The proof: a planted secret never reaches the output
# --------------------------------------------------------------------------


def test_a_planted_key_never_reaches_the_log_file(_isolated_logging: Path) -> None:
    """The whole point of spec 08 step 3, exercised five different ways.

    Each of these is a way a key has actually escaped in real systems: as a
    named field, buried in a nested payload, interpolated into a message, inside
    an exception, and emitted by a third-party library through the stdlib logger.
    """
    log_path = _isolated_logging
    assert register_secret(PLANTED_KEY)
    assert register_secret(PLANTED_SECRET)

    log = get_logger("test")
    log.info("named field", api_key=PLANTED_KEY, api_secret=PLANTED_SECRET)
    log.info("nested", request={"headers": {"API-Key": PLANTED_KEY}, "nonce": 1735689600000000})
    log.info(f"interpolated into the message: {PLANTED_KEY}")
    log.info("in a list", candidates=[{"key": PLANTED_KEY}, {"other": PLANTED_SECRET}])
    try:
        raise RuntimeError(f"kraken rejected {PLANTED_KEY}")
    except RuntimeError:
        log.exception("exception message")
    logging.getLogger("some.third.party").warning("foreign record with %s", PLANTED_KEY)

    raw = log_path.read_text(encoding="utf-8")
    assert PLANTED_KEY not in raw
    assert PLANTED_SECRET not in raw
    assert REDACTION in raw
    # And the lines are still usable log lines, not mangled bytes.
    assert len(_read_lines(log_path)) == 6


def test_key_name_redaction_works_without_registration(_isolated_logging: Path) -> None:
    """Mechanism 1 alone: a field named like a credential goes, registered or not.

    This is the case where nobody remembered to call `register_secret`, which is
    the case that actually happens.
    """
    log_path = _isolated_logging
    assert registered_secret_count() == 0
    get_logger("test").info("unregistered", api_key="whatever-this-is", nonce=12345)
    line = _read_lines(log_path)[0]
    assert line["api_key"] == REDACTION
    assert line["nonce"] == REDACTION
    assert "whatever-this-is" not in log_path.read_text(encoding="utf-8")


def test_value_scrubbing_works_where_key_names_cannot(_isolated_logging: Path) -> None:
    """Mechanism 2 alone: the field name is innocent, the value is not."""
    log_path = _isolated_logging
    register_secret(PLANTED_KEY)
    get_logger("test").info("innocent field name", detail=f"used {PLANTED_KEY} to sign")
    raw = log_path.read_text(encoding="utf-8")
    assert PLANTED_KEY not in raw
    assert REDACTION in raw


def test_redaction_survives_nesting_and_sequences() -> None:
    from acsoe.platform.logging import redact_secret_keys

    event = {
        "event": "x",
        "outer": {"inner": [{"signature": "sig"}, {"safe": 1}]},
        "tuple_field": ({"token": "t"},),
    }
    result = redact_secret_keys(None, "info", dict(event))
    assert result["outer"]["inner"][0]["signature"] == REDACTION
    assert result["outer"]["inner"][1]["safe"] == 1
    assert result["tuple_field"][0]["token"] == REDACTION


def test_a_short_value_is_refused_rather_than_registered() -> None:
    """Scrubbing "0" from every line would destroy the logs and protect nothing."""
    clear_secrets()
    assert register_secret("0") is False
    assert register_secret("") is False
    assert register_secret(None) is False
    assert register_secret("x" * (MIN_SECRET_LENGTH - 1)) is False
    assert register_secret("x" * MIN_SECRET_LENGTH) is True


def test_longest_secret_is_scrubbed_first() -> None:
    """A short secret contained inside a longer one must not leave a fragment."""
    clear_secrets()
    register_secret("abcdefgh")
    register_secret("abcdefghijklmnop")
    assert scrub_text("value=abcdefghijklmnop") == f"value={REDACTION}"


def test_registered_secret_count_never_exposes_a_secret() -> None:
    clear_secrets()
    register_secret(PLANTED_KEY)
    assert registered_secret_count() == 1


# --------------------------------------------------------------------------
# Structure: JSON, one event per line, run_id and cycle_id bound
# --------------------------------------------------------------------------


def test_output_is_one_json_object_per_line(_isolated_logging: Path) -> None:
    log_path = _isolated_logging
    log = get_logger("test")
    log.info("first")
    log.info("second")
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        assert isinstance(json.loads(line), dict)


def test_every_loop_line_carries_run_id_and_cycle_id(_isolated_logging: Path) -> None:
    """`code-standards.md`: every log line inside the loop carries both."""
    log_path = _isolated_logging
    bind_run("run-abc")
    bind_cycle("cycle-1")
    get_logger("engine").info("gate_blocked", engine="cost", net_edge=-0.0021)
    line = _read_lines(log_path)[0]
    assert line["run_id"] == "run-abc"
    assert line["cycle_id"] == "cycle-1"
    assert line["event"] == "gate_blocked"
    assert line["level"] == "info"
    assert isinstance(line["ts"], str)


def test_cycle_id_is_dropped_between_ticks(_isolated_logging: Path) -> None:
    """Otherwise a between-ticks line claims to belong to the tick that just ended."""
    log_path = _isolated_logging
    bind_run("run-abc")
    bind_cycle("cycle-1")
    clear_cycle()
    get_logger("engine").info("between ticks")
    line = _read_lines(log_path)[0]
    assert line["run_id"] == "run-abc"
    assert "cycle_id" not in line


def test_third_party_records_are_captured_as_json(_isolated_logging: Path) -> None:
    """uvicorn and websockets log through the stdlib; those lines must be JSON
    and must go through the same redaction."""
    log_path = _isolated_logging
    logging.getLogger("websockets.client").warning("connection closed")
    line = _read_lines(log_path)[0]
    assert line["event"] == "connection closed"
    assert line["logger"] == "websockets.client"


def test_configure_logging_creates_the_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "logs"
    assert not target.exists()
    path = configure_logging(log_dir=target)
    assert target.is_dir()
    assert path.parent == target


def test_reconfiguring_does_not_duplicate_handlers(tmp_path: Path) -> None:
    """A daemon restart inside one process must not write every line twice."""
    configure_logging(log_dir=tmp_path / "logs")
    configure_logging(log_dir=tmp_path / "logs")
    assert len(logging.getLogger().handlers) == 1


def test_daily_rotation_is_configured(_isolated_logging: Path) -> None:
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.handlers.TimedRotatingFileHandler)
    assert handler.when == "MIDNIGHT"
    assert handler.utc is True
    assert handler.backupCount == 14


# --------------------------------------------------------------------------
# Runtime directories
# --------------------------------------------------------------------------


def test_runtime_directories_are_created(tmp_path: Path) -> None:
    paths = ensure_runtime_directories(tmp_path)
    for directory in paths.all():
        assert directory.is_dir()
    assert paths.raw == tmp_path.resolve() / "data" / "raw"
    assert paths.historical == tmp_path.resolve() / "data" / "historical"
    assert paths.derived == tmp_path.resolve() / "data" / "derived"
    assert paths.db == tmp_path.resolve() / "data" / "db"
    assert paths.logs == tmp_path.resolve() / "logs"
    assert paths.models == tmp_path.resolve() / "models"


def test_creating_runtime_directories_is_idempotent(tmp_path: Path) -> None:
    """Called on every daemon start; a second start must not be an error."""
    first = ensure_runtime_directories(tmp_path)
    (first.raw / "existing.jsonl").write_text("{}\n", encoding="utf-8")
    second = ensure_runtime_directories(tmp_path)
    assert first == second
    assert (second.raw / "existing.jsonl").read_text(encoding="utf-8") == "{}\n"


def test_runtime_paths_creates_nothing(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    assert not paths.raw.exists()


def test_the_models_root_is_created_beside_data_and_logs(tmp_path: Path) -> None:
    """Spec 61 step 3, and this test used to assert the exact opposite.

    Spec 08 named five directories and left `models/` out on the argument that the
    training pipeline owns the run-id naming, so creating the root empty would
    suggest a contract that did not exist. The contract exists now: B's
    `StoreClient` takes a `models_dir` and hands out `models/<run_id>/`, and A's
    CLI passes it in. Creating the root is A's; everything inside it is C's.

    Beside `data/` rather than inside it, because `data/` holds rebuildable output
    and a trained artefact is not rebuildable from anything the archive carries.

    Empty is the normal state on a fresh clone: the three `models.*_run_id` keys
    are absent, the engines block, and the daemon still records.
    """
    paths = ensure_runtime_directories(tmp_path)
    assert paths.models.is_dir()
    assert paths.models == tmp_path.resolve() / "models"
    assert not any(paths.models.iterdir()), "the root is created empty; artefacts are C's"
