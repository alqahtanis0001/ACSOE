"""The string side of the number rules in ``context/ui-context.md``.

Those rules are not stylistic. "Misread numbers cost money" is the first line of
that section, and every function here exists because of one of its six rules:

1. Tabular figures are CSS, not Python — that one lives in ``static/console.css``.
2. **Percentages are always explicitly signed.** :func:`format_signed_pct` writes
   ``+0.62%`` and never a bare ``0.62%``.
3. Colour is never the only signal, which is why the sign is written into the
   string rather than left to a class name.
4. Money renders to the precision it was stored at. :func:`format_money`
   therefore never re-rounds and never quantizes.
5. Anything older than ``console.stale_after_ms`` shows its age beside it —
   :func:`format_age`.
6. **A proper minus sign, U+2212, never a hyphen.** A hyphen is narrower than a
   digit in almost every face, so a column of hyphen-negative numbers does not
   align even with tabular figures switched on.

Nothing here touches ``float``. ``Decimal`` arrives, a string leaves, and the two
are the only types in the module. A money value that passed through ``float``
anywhere on that path would already have lost the precision the rules exist to
protect.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from acsoe.clients.store.contracts import from_micros

__all__ = [
    "MINUS_SIGN",
    "NO_REASON_RECORDED",
    "OUTCOME_WORDS",
    "PERCENT_PLACES",
    "REASON_PROSE",
    "format_age",
    "format_clock_time",
    "format_money",
    "format_outcome",
    "format_rate_pct",
    "format_signed_pct",
    "format_timestamp",
    "operator_reason",
    "signed",
]

#: U+2212 MINUS SIGN. Written as a named escape rather than as the character
#: itself, for two reasons: this file stays ASCII, and a reader cannot mistake it
#: for the hyphen it is one pixel away from looking like. That distinction is the
#: whole point of rule 6.
MINUS_SIGN: Final = "\N{MINUS SIGN}"

#: Two decimal places on a percentage. The system's edges are fractions of a
#: percent, so one place would round a real edge away and three would suggest a
#: precision the model does not have.
PERCENT_PLACES: Final = 2

_SECONDS = 1_000
_MINUTES = 60 * _SECONDS
_HOURS = 60 * _MINUTES
_DAYS = 24 * _HOURS


def signed(text: str) -> str:
    """Replace a leading ASCII hyphen with a proper minus sign.

    Applied to the *rendered* string rather than to the number, because
    ``Decimal.__str__`` is the thing that writes the hyphen and it is the only
    place one can enter.
    """
    return MINUS_SIGN + text[1:] if text.startswith("-") else text


def format_money(value: Decimal, *, currency: str | None = None) -> str:
    """A money value at exactly the precision it was stored at.

    No quantizing. ``Decimal("1000.00")`` means cents and ``Decimal("1000")``
    means units; the trailing zeros are the quantum the writer chose, and
    normalising them away throws information that came from the exchange's own
    ``pair_decimals``. ``format(value, "f")`` also refuses scientific notation,
    which ``str(Decimal("1E+3"))`` would otherwise produce.

    A non-finite value is not formatted. ``Decimal("NaN")`` would render as the
    text ``NaN`` and sit in a column of prices looking like a value.
    """
    if not value.is_finite():
        raise ValueError(f"refusing to render a non-finite money value: {value!r}")
    rendered = signed(format(value, "f"))
    return rendered if currency is None else f"{rendered} {currency}"


def format_signed_pct(value: Decimal, *, places: int = PERCENT_PLACES) -> str:
    """A ratio rendered as an explicitly signed percentage.

    The argument is a **ratio**, per ``code-standards.md``: ``Decimal("0.0062")``
    is 0.62% and renders ``+0.62%``. Passing ``0.62`` and getting ``+62.00%`` is
    correct behaviour, not a bug — the unit belongs to the caller and the variable
    name is where it is declared.

    Zero renders ``+0.00%``. That looks odd and is deliberate: rule 2 says always
    explicitly signed, and a bare ``0.00%`` in a column of signed figures reads as
    a missing value rather than as a flat one.
    """
    if not value.is_finite():
        raise ValueError(f"refusing to render a non-finite percentage: {value!r}")
    if places < 0:
        raise ValueError("places must not be negative")
    exponent = Decimal(1).scaleb(-places)
    percent = (value * 100).quantize(exponent, rounding=ROUND_HALF_UP)
    if percent.is_signed() and percent != 0:
        return MINUS_SIGN + format(-percent, "f") + "%"
    # `is_signed()` is true for Decimal("-0.00"), which must not print as a
    # negative zero: the sign would be reporting a direction the number does not
    # have.
    return "+" + format(abs(percent), "f") + "%"


def format_age(milliseconds: int) -> str:
    """How old a figure is, in the shortest honest form.

    Shown beside any figure past ``console.stale_after_ms``. Deliberately coarse:
    the operator needs to know whether the screen is seconds or minutes behind,
    and a millisecond-precision age on a one-minute loop is noise that changes on
    every poll.

    A negative age is rendered as ``0s`` rather than refused. It means the clock
    the console was given is behind a timestamp the daemon wrote, which is a
    two-process skew and not something the console can fix or should crash over.
    """
    remaining = max(milliseconds, 0)
    if remaining < _SECONDS:
        return f"{remaining}ms"
    if remaining < _MINUTES:
        return f"{remaining // _SECONDS}s"
    if remaining < _HOURS:
        return f"{remaining // _MINUTES}m {(remaining % _MINUTES) // _SECONDS:02d}s"
    if remaining < _DAYS:
        return f"{remaining // _HOURS}h {(remaining % _HOURS) // _MINUTES:02d}m"
    return f"{remaining // _DAYS}d {(remaining % _DAYS) // _HOURS:02d}h"
