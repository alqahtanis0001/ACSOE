"""The number rules of `ui-context.md`, made executable. Spec 17 step 7.

"These are not stylistic. Misread numbers cost money." Each test below names the
rule it is enforcing, because in six months the rule is what matters and the
assertion is only how it is checked.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from acsoe.console.format import (
    MINUS_SIGN,
    format_age,
    format_money,
    format_signed_pct,
    signed,
)

#: The character rule 6 requires. Written here as a codepoint rather than as the
#: glyph, so a test that started passing because someone pasted a hyphen would
#: fail rather than look right.
U2212 = "−"
HYPHEN = "-"


def test_the_minus_sign_is_u2212_and_not_a_hyphen() -> None:
    """Rule 6. A hyphen is narrower than a digit in almost every face, so a column
    of hyphen-negative numbers does not align even with tabular figures on."""
    assert MINUS_SIGN == U2212
    assert MINUS_SIGN != HYPHEN
    assert ord(MINUS_SIGN) == 0x2212


# --------------------------------------------------------------------------- #
# Percentages
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        ("0.0062", "+0.62%"),
        ("-0.0150", U2212 + "1.50%"),
        ("0", "+0.00%"),
        ("-0.00001", "+0.00%"),
        ("0.5", "+50.00%"),
        ("-1", U2212 + "100.00%"),
    ],
)
def test_a_percentage_is_always_explicitly_signed(ratio: str, expected: str) -> None:
    """Rule 2, and the two examples `ui-context.md` gives by name.

    The argument is a **ratio**: `code-standards.md` stores percentages as
    decimals, so 0.0062 is 0.62%. The `-0.00001` case is the interesting one - it
    rounds to zero, and a zero that printed as negative would be reporting a
    direction the number does not have.
    """
    assert format_signed_pct(Decimal(ratio)) == expected


def test_a_percentage_never_carries_a_hyphen() -> None:
    """Rule 3 depends on this: the sign carries the meaning, colour only reinforces
    it, so a colourblind operator must be able to read the sign at a glance."""
    rendered = format_signed_pct(Decimal("-0.0150"))
    assert HYPHEN not in rendered
    assert rendered.startswith(U2212)


def test_a_non_finite_percentage_is_refused() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        format_signed_pct(Decimal("NaN"))


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("1000.00", "1000.00"),
        ("1000", "1000"),
        ("0.00000001", "0.00000001"),
        ("-12.34", U2212 + "12.34"),
        ("1E+3", "1000"),
    ],
)
def test_money_renders_at_the_precision_it_was_stored_at(stored: str, expected: str) -> None:
    """Rule 4, and `money_to_text`'s reasoning read from the other end.

    The trailing zeros are the quantum the writer chose: `1000.00` means cents and
    `1000` means units, and normalising the difference away throws precision that
    came from the exchange's own `pair_decimals`. `1E+3` is the same number in
    scientific notation and must never reach a screen that way.
    """
    assert format_money(Decimal(stored)) == expected


def test_money_never_passes_through_float() -> None:
    """A float that reached here would already have lost the precision.

    `0.1 + 0.2` is the canonical demonstration; asserted against the exact decimal
    string rather than with `pytest.approx`, per `code-standards.md`.
    """
    exact = Decimal("0.1") + Decimal("0.2")
    assert format_money(exact) == "0.3"
    assert format_money(Decimal(str(0.1 + 0.2))) != "0.3"


def test_money_can_carry_its_currency() -> None:
    assert format_money(Decimal("896.67"), currency="USD") == "896.67 USD"


def test_a_non_finite_money_value_is_refused() -> None:
    """`Decimal("NaN")` would render as the text `NaN` and sit in a column of
    prices looking like a value."""
    with pytest.raises(ValueError, match="non-finite"):
        format_money(Decimal("Infinity"))


def test_signed_only_touches_a_leading_hyphen() -> None:
    assert signed("-1.5") == U2212 + "1.5"
    assert signed("1-5") == "1-5"
    assert signed("") == ""


# --------------------------------------------------------------------------- #
# Age
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("ms", "expected"),
    [
        (0, "0ms"),
        (999, "999ms"),
        (1_000, "1s"),
        (59_999, "59s"),
        (60_000, "1m 00s"),
        (125_000, "2m 05s"),
        (3_600_000, "1h 00m"),
        (86_400_000, "1d 00h"),
    ],
)
def test_age_is_coarse_on_purpose(ms: int, expected: str) -> None:
    """Rule 5 shows the age beside a stale figure.

    Deliberately coarse: the operator needs to know whether the screen is seconds
    or minutes behind, and a millisecond-precision age on a one-minute loop is
    noise that changes on every poll.
    """
    assert format_age(ms) == expected


def test_a_negative_age_does_not_crash_the_screen() -> None:
    """It means the console's clock is behind a timestamp the daemon wrote.

    That is a two-process skew. The console cannot fix it and must not take the
    status band down over it.
    """
    assert format_age(-5_000) == "0ms"
