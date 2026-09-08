"""Structured logging, and the one place secrets are removed.

``structlog``, JSON, one event per line, written to ``logs/`` with daily
rotation. ``logs/`` is gitignored; a log is never committed.

**Redaction lives here, at the client boundary, and not at call sites.**
Invariant 13 and ``code-standards.md`` both say so, and the reason is that a
rule enforced at call sites is a rule enforced by whoever remembers it. There
are two independent mechanisms, because either one alone has a hole:

1. **Key-name redaction.** Any field whose *name* looks like a credential is
   replaced, recursively through nested dicts and lists. This catches
   ``log.info("auth", api_key=key)``.
2. **Value scrubbing.** Any *value* registered through :func:`register_secret`
   is removed from the fully rendered line, whatever field it appears in and
   however deeply it was nested. This catches ``log.info(f"login failed for
   {key}")`` and, more importantly, a key that leaks through a formatted
   exception message — which key-name redaction cannot see at all.

The proof that this works is ``tests/platform/test_logging.py``, which plants a
secret and asserts it never reaches the file. It is not a code review.
"""

from __future__ import annotations

import logging
import logging.handlers
import threading
from pathlib import Path
from typing import Any, Final

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

REDACTION: Final = "<redacted>"

#: A field whose name contains any of these is redacted, recursively.
#:
#: Deliberately over-broad. A false positive costs one log field; a false
#: negative puts an API key in a file that goes into a public repository and a
#: dissertation. When in doubt the answer is to redact.
SECRET_KEY_TOKENS: Final = (
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "password",
    "passphrase",
    "token",
    "nonce",
    "signature",
    "api_sign",
    "authorization",
    "credential",
    "private_key",
    "otp",
    "key",
    "sign",
    "auth",
)

#: Shorter than this and a "secret" is more likely to be a placeholder, an empty
#: string, or a single digit. Scrubbing ``"0"`` from every line would destroy the
#: logs while protecting nothing, so short values are refused rather than
#: registered.
MIN_SECRET_LENGTH: Final = 8

_LOG_FILENAME: Final = "acsoe.jsonl"

_secret_lock = threading.Lock()
_secrets: set[str] = set()
#: Longest first, so a secret that contains another is replaced whole.
_secrets_ordered: tuple[str, ...] = ()


def register_secret(value: str | None) -> bool:
    """Register a value that must never appear in a log line.

    Returns True if it was registered. Called by ``platform/config.py``, the one
    module that reads the environment, at the moment a credential enters the
    process — so the logger is armed before any client that could log it exists.

    Never logs, prints or echoes the value it is given.
    """
    global _secrets_ordered
    if value is None:
        return False
    candidate = value.strip()
    if len(candidate) < MIN_SECRET_LENGTH:
        return False
    with _secret_lock:
        if candidate in _secrets:
            return True
        _secrets.add(candidate)
        _secrets_ordered = tuple(sorted(_secrets, key=len, reverse=True))
    return True


def registered_secret_count() -> int:
    """How many secrets are armed. Never exposes one — only the count."""
    with _secret_lock:
        return len(_secrets)


def clear_secrets() -> None:
    """Test hook. Not called by the running system."""
    global _secrets_ordered
    with _secret_lock:
        _secrets.clear()
        _secrets_ordered = ()


def scrub_text(text: str) -> str:
    """Remove every registered secret from a rendered line."""
    for secret in _secrets_ordered:
        if secret in text:
            text = text.replace(secret, REDACTION)
    return text


def _is_secret_key(name: object) -> bool:
    lowered = str(name).lower()
    return any(token in lowered for token in SECRET_KEY_TOKENS)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (REDACTION if _is_secret_key(key) else _redact_value(inner))
            for key, inner in value.items()
        }
    if isinstance(value, (list, tuple)):
        rebuilt = [_redact_value(item) for item in value]
        return type(value)(rebuilt) if isinstance(value, tuple) else rebuilt
    return value


def redact_secret_keys(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """structlog processor: redact any field whose name looks like a credential."""
    redacted = _redact_value(dict(event_dict))
    assert isinstance(redacted, dict)
    return redacted


class ScrubbingJSONRenderer:
    """Render to JSON, then scrub registered secret values from the whole line.

    Scrubbing the *rendered* string rather than the event dict is deliberate: by
    that point exception tracebacks, formatted messages and nested payloads are
    all flat text, so there is nowhere left for a registered value to hide.
    """

    def __init__(self) -> None:
        self._inner = structlog.processors.JSONRenderer(sort_keys=False)

    def __call__(self, logger: WrappedLogger, name: str, event_dict: EventDict) -> str:
        rendered = self._inner(logger, name, event_dict)
        if isinstance(rendered, bytes):
            rendered = rendered.decode("utf-8")
        return scrub_text(rendered)


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        # `ts` is the wall-clock time the line was written, which is an
        # operational fact about the process. It is NOT `context.now`: an engine
        # logging inside a replay binds that itself, so a replayed log carries
        # both the simulated instant and the real one.
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_secret_keys,
    ]


def configure_logging(
    *,
    log_dir: Path,
    level: str = "INFO",
    retention_days: int = 14,
    also_stderr: bool = False,
) -> Path:
    """Configure structlog and the stdlib root logger. Returns the log file path.

    Rotates at UTC midnight and keeps ``retention_days`` files. The root logger
    is configured rather than a named one, so third-party output — uvicorn,
    websockets — lands in the same JSON file and goes through the same
    redaction. A key leaking out of somebody else's library is still a key.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / _LOG_FILENAME

    formatter = structlog.stdlib.ProcessorFormatter(
        # Applied to records that came from the stdlib rather than structlog.
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            redact_secret_keys,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            ScrubbingJSONRenderer(),
        ],
    )

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_path),
        when="midnight",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setFormatter(formatter)

    handlers: list[logging.Handler] = [file_handler]
    if also_stderr:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
        existing.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level.upper())

    structlog.configure(
        processors=[
            *_shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # False on purpose: reconfiguring between tests must actually take
        # effect, and a cached logger bound to a closed handler is a silent
        # loss of log lines.
        cache_logger_on_first_use=False,
    )
    return log_path


def get_logger(name: str = "acsoe") -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def bind_run(run_id: str) -> None:
    """Bind ``run_id`` for the life of the process.

    ``code-standards.md``: every log line inside the loop carries ``cycle_id``
    and ``run_id``. Binding them into the context rather than passing them at
    each call site is what makes that true rather than aspirational.
    """
    structlog.contextvars.bind_contextvars(run_id=run_id)


def bind_cycle(cycle_id: str) -> None:
    """Bind ``cycle_id`` for the current tick. Call once per tick."""
    structlog.contextvars.bind_contextvars(cycle_id=cycle_id)


def clear_cycle() -> None:
    """Drop ``cycle_id`` at the end of a tick so a between-ticks line cannot
    claim to belong to the tick that just finished."""
    structlog.contextvars.unbind_contextvars("cycle_id")


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
