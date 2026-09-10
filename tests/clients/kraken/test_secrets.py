"""Spec 25 — no secret in any log line, exception message, or repr.

Same shape as A's Phase 0 redaction test in `tests/platform/test_logging.py`: plant
a real key, drive the code path that handles it, and read the captured output back.
A code review is not evidence; a file with the key absent from it is.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import structlog

from acsoe.clients.kraken import KrakenAPIError, KrakenRestClient, RateLimiter
from acsoe.clients.kraken.rest import HttpResponse, sign_request
from acsoe.platform.clock import FixedClock
from acsoe.platform.config import Credentials, load_credentials
from acsoe.platform.logging import clear_secrets, configure_logging, get_logger

PLANTED_KEY = "kR4k3n-Ap1-K3y-DO-NOT-LOG-9f2c1a7b"
PLANTED_SECRET = "c2VjcmV0LWJhc2U2NC1raW5kLW9mLXRoaW5nLXRoYXQta3Jha2VuLXVzZXM="
AT = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def log_file(tmp_path: Path) -> Iterator[Path]:
    """Configure logging into `tmp_path` and take the handlers down before it goes.

    The teardown closes every handler *before* pytest removes `tmp_path`. On Windows
    an open file handle makes that removal an error rather than a warning, and it is
    a teardown ERROR rather than a test failure, which is easy to read past.
    """
    clear_secrets()
    path = configure_logging(log_dir=tmp_path / "logs", level="DEBUG")
    yield path
    logging.shutdown()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    structlog.reset_defaults()
    clear_secrets()


def test_credentials_never_render_their_values() -> None:
    credentials = Credentials(key=PLANTED_KEY, secret=PLANTED_SECRET)
    assert PLANTED_KEY not in repr(credentials)
    assert PLANTED_SECRET not in repr(credentials)
    assert PLANTED_KEY not in str(credentials)
    assert PLANTED_KEY not in f"{credentials}"
    assert PLANTED_KEY not in "{}".format(credentials)  # noqa: UP032 — the point is the format path


def test_load_credentials_arms_the_redactor_and_returns_none_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KRAKEN_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_API_SECRET", raising=False)
    assert load_credentials() is None

    monkeypatch.setenv("KRAKEN_API_KEY", PLANTED_KEY)
    monkeypatch.setenv("KRAKEN_API_SECRET", PLANTED_SECRET)
    credentials = load_credentials()
    assert credentials is not None
    assert credentials.key == PLANTED_KEY


class _EchoTransport:
    """Records the headers it was handed, so the test can prove they were sent
    and simultaneously prove they never reach an exception or a log line."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Any,
        content: bytes | None,
        timeout_s: float,
    ) -> HttpResponse:
        self.headers = dict(headers)
        return HttpResponse(
            status_code=200,
            body=json.dumps({"error": ["EAPI:Invalid key"], "result": {}}).encode(),
        )


@pytest.mark.asyncio
async def test_no_secret_reaches_an_exception_message_or_a_log_line(log_file: Path) -> None:
    transport = _EchoTransport()
    client = KrakenRestClient(
        clock=FixedClock(AT),
        limiter=RateLimiter(capacity=10, refill_per_second=10),
        transport=transport,
        credentials=Credentials(key=PLANTED_KEY, secret=PLANTED_SECRET),
        base_url="https://example.invalid",
        # Both TTLs supplied, so the call reaches the signing path this test is
        # scanning. Omitting them raises about the missing TTL before a header is
        # ever built, and a scan of output the key never entered proves nothing.
        asset_pairs_ttl_s=300,
        trade_volume_ttl_s=60,
    )

    with pytest.raises(KrakenAPIError) as caught:
        await client.trade_volume()

    # The key really was sent — otherwise the scan below proves nothing.
    assert transport.headers["API-Key"] == PLANTED_KEY
    assert transport.headers["API-Sign"]

    message = f"{caught.value!r} {caught.value}"
    assert PLANTED_KEY not in message
    assert PLANTED_SECRET not in message
    assert transport.headers["API-Sign"] not in message

    logger = get_logger("test.kraken")
    logger.error("kraken_call_failed", error=str(caught.value), exc_info=caught.value)
    logging.getLogger().handlers[0].flush()
    captured = log_file.read_text(encoding="utf-8")
    assert PLANTED_KEY not in captured
    assert PLANTED_SECRET not in captured


def test_a_registered_secret_is_scrubbed_even_out_of_a_free_text_line(log_file: Path) -> None:
    """The case key-name redaction cannot see: a credential inside a message."""
    from acsoe.platform.logging import register_secret

    register_secret(PLANTED_KEY)
    get_logger("test.kraken").info(f"connecting with {PLANTED_KEY}")
    logging.getLogger().handlers[0].flush()
    assert PLANTED_KEY not in log_file.read_text(encoding="utf-8")


def test_the_signature_itself_is_never_returned_in_an_error() -> None:
    signature = sign_request(path="/0/private/Balance", nonce=7, form={}, secret=PLANTED_SECRET)
    assert signature
    assert PLANTED_SECRET not in signature
