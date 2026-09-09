"""The exchange-shaped exceptions, in one place.

Three types, and the hierarchy matters more than the names. Every caller that has
to fail closed catches :class:`KrakenError` and blocks; the two subclasses exist so
a caller that genuinely needs to tell an application rejection from an outage can,
without anybody having to catch ``Exception``.

``tests/harness/fake_kraken.py`` imports these three names from
``acsoe.clients.kraken`` and falls back to its own definitions only while this
module does not exist. That is why the constructor signatures are fixed here:
``KrakenAPIError(message, errors)`` and ``KrakenUnavailableError(message, cause)``.
A test that asserts on ``exc.errors`` keeps asserting on the same attribute across
the Phase 2 handover, which is the whole point of the fake raising the real type.

**Nothing here ever carries a credential.** ``__str__`` and ``__repr__`` are the two
places a key leaks into a log without anyone writing a log line, so the request
context these errors carry is the method and the *path* only — never a header,
never a body, never a query string, and never the signed nonce.
"""

from __future__ import annotations

__all__ = ["KrakenAPIError", "KrakenError", "KrakenUnavailableError"]


class KrakenError(Exception):
    """Base class, so a caller failing closed catches one exchange-shaped type."""


class KrakenAPIError(KrakenError):
    """The envelope came back with a non-empty ``error`` list.

    Raised regardless of HTTP status. Kraken answers 200 with a populated ``error``
    array and does not use the status code to signal application errors, so a client
    that treats 2xx as success records rejections as fills.
    """

    def __init__(self, message: str, errors: list[str]) -> None:
        super().__init__(message)
        self.errors = errors


class KrakenUnavailableError(KrakenError):
    """Transport, timeout, disconnect, malformed body, or exhausted rate limit.

    Everything that means "we did not get an answer", as opposed to "we got an
    answer and it was no". Both block; only this one is worth retrying.
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause
