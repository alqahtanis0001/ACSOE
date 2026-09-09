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

**No money value here ever touches ``float``.** ``Decimal`` arrives, a string
leaves, and a money value that passed through ``float`` anywhere on that path
would already have lost the precision these rules exist to protect. The single
``float`` in the module is :func:`format_rate_pct`, which renders the
leaderboard's *statistics* — a win rate is not money and was never a ``Decimal``.

Two things here are not number rules but belong with them, because they are the
same kind of decision: :func:`operator_reason`, which is why a code never reaches
the screen, and :func:`format_outcome`, which is why ``target`` reads ``Target``.
Both are copy rules from the same document, and both exist so that no screen
decides for itself what a stored code says to a human.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from acsoe.clients.store.contracts import from_micros

__all__ = [
    "ABSENT",
    "DIRECTION_FLAT",
    "DIRECTION_NEGATIVE",
    "DIRECTION_POSITIVE",
    "MINUS_SIGN",
    "NO_REASON_RECORDED",
    "OUTCOME_WORDS",
    "PERCENT_PLACES",
    "REASON_PROSE",
    "direction",
    "format_age",
    "format_clock_time",
    "format_engine_name",
    "format_metric",
    "format_money",
    "format_optional_pct",
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

#: `reason_code` to the sentence an operator reads, per rule 3 of the copy
#: section of ``ui-context.md``: "Rejection reasons are written for the operator,
#: not the log". The table exists so that a row whose stored ``reason`` is a bare
#: code — which the engines are free to write, since nothing constrains that
#: column — still reaches the screen as a sentence.
#:
#: Every entry is a plain restatement of what the code already says. **Nothing
#: here adds a number, a threshold or a cause the row did not carry**, because a
#: sentence invented in the view layer is a sentence nothing verifies.
REASON_PROSE: Final[Mapping[str, str]] = {
    "net_edge_below_hurdle": "Net edge did not clear the hurdle after fees",
    # The two fail-closed paths, deliberately not variants of the lines around
    # them. "The edge was too thin" is a normal Tuesday and this system refusing
    # almost everything is the point; "the gate could not reach its inputs" is a
    # data problem the operator may need to act on, and invariant 3 is why it
    # reads as a refusal either way. Requested by B for engines 10 and 11,
    # 2026-09-09; B's wording, kept verbatim so the producer and the consumer
    # cannot drift.
    "cost_inputs_unavailable": "The cost gate could not price this candidate",
    "risk_inputs_unavailable": "The risk gate could not size this candidate",
    "spread_wider_than_move": "The spread is wider than the expected move",
    "below_ordermin": "Position would be below the pair's minimum order size",
    "below_costmin": "Position value would be below the pair's minimum order value",
    "insufficient_quote_balance": "Not enough quote currency held to open this position",
    "max_concurrent_positions": "Already holding the maximum number of positions",
    "outside_universe": "Pair is outside the tradable universe at this balance",
    "meta_label_veto": "The skeptic vetoed this entry",
    "outlier_market_state": "Market state is an outlier",
    "dissimilarity_index": "Conditions are unlike anything in training",
    "insufficient_depth": "Order book is too thin to fill without slippage",
    "no_candidate_cleared": "Nothing cleared the gates on this bar",
    # Engine 4 `data_guard`, requested by A on 2026-09-09. Codes fixed by A so the
    # producer and the consumer cannot drift; prose is mine, and A's wording is kept
    # almost verbatim because it was already right.
    #
    # `missing_candle` is about a hole *inside* the published series, which reads
    # like a contradiction of `architecture-context.md` — a missing candle in the
    # historical archive means no trades occurred and is not a data error, and spec
    # 30 forbids the loader from inventing one. Both hold at once: the loader
    # refuses to invent a bar, the gate refuses to act on a series with a hole in
    # it. One is about labelling, the other about trading, and fail-closed points
    # the opposite way in each. Engine 4's README carries the same note.
    "market_data_stale": "Market data is older than the guard allows",
    "negative_spread": "The order book is crossed",
    "missing_candle": "A decision bar has no candle",
}

#: What a row with neither prose nor a mapped code shows. A statement of absence,
#: in the voice of the empty state — never the bare code, and never a guess at
#: what the engine meant.
NO_REASON_RECORDED: Final = "No reason was recorded."

#: `TradeOutcome` to the operator word. The stored value is a code; the screen
#: says which barrier the position hit.
OUTCOME_WORDS: Final[Mapping[str, str]] = {
    "target": "Target",
    "stop": "Stop",
    "timeout": "Timeout",
    "liquidation": "Liquidation",
}

#: `snake_case_like_this` and nothing else. Used only to decide whether a stored
#: ``reason`` is a sentence or a code that leaked into the column; it is never
#: used to *derive* prose.
_CODE_LIKE: Final = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")

#: What a cell shows when the row does not carry the value. An em dash, which
#: reads as *absent*; a zero in a numeric column reads as a measured result, and
#: a `scout` rejection that never reached the cost gate has no net edge to report.
ABSENT: Final = "\N{EM DASH}"

#: The three directions a signed figure can have. These are the class names the
#: stylesheet keys its 2px rule off — the **sign** in the text carries the meaning
#: and the colour only reinforces it, so a red-green colourblind operator loses
#: nothing by never seeing them.
DIRECTION_POSITIVE: Final = "pos"
DIRECTION_NEGATIVE: Final = "neg"
DIRECTION_FLAT: Final = "flat"


def direction(value: Decimal | None) -> str:
    """Which way a signed figure points, as a class name.

    Zero is :data:`DIRECTION_FLAT` and not "positive". A flat outcome is neither
    a gain nor a loss, and colouring it green would overstate it — which is the
    same reason the palette's positive and negative are muted in the first place.
    """
    if value is None or not value.is_finite() or value == 0:
        return DIRECTION_FLAT
    return DIRECTION_NEGATIVE if value < 0 else DIRECTION_POSITIVE


def format_engine_name(name: str) -> str:
    """An engine's identifier as the operator reads it: ``data_guard`` -> "data guard".

    Not title-cased. The engines are named after what they do, and "Data Guard"
    reads like a product while "data guard" reads like a part of the system —
    which matches the sentence-case rule in ``ui-context.md``.
    """
    return name.strip().replace("_", " ")


def format_optional_pct(value: Decimal | None, *, places: int = PERCENT_PLACES) -> str:
    """A signed percentage, or :data:`ABSENT` when the row does not carry one."""
    return ABSENT if value is None else format_signed_pct(value, places=places)


def operator_reason(reason_code: str, reason: str = "") -> str:
    """The sentence the operator reads for one refused candidate or blocked tick.

    Three sources, in this order, and the order is a decision worth stating:

    1. **The row's own ``reason``, when it is already prose.** It is the most
       specific text available — "Net edge -0.21% after fees" carries the actual
       number, and no mapping keyed on a code ever can. Replacing it with the
       generic sentence for its code would throw away information the writer took
       the trouble to record.
    2. **:data:`REASON_PROSE` for the code**, when the stored text is empty or is
       itself a bare code. That is the case the mapping exists for.
    3. **:data:`NO_REASON_RECORDED`** when there is neither. Not the code — a code
       on screen is the defect this function exists to prevent — and not an
       invented sentence either.
    """
    text = reason.strip()
    if text and not _CODE_LIKE.match(text):
        return text
    mapped = REASON_PROSE.get(reason_code.strip())
    if mapped:
        return mapped
    return NO_REASON_RECORDED


def format_outcome(outcome: str) -> str:
    """The operator word for a stored outcome code.

    An unmapped value is title-cased rather than mapped to a guess: a new barrier
    the console has not been taught about should read as itself, not as one of the
    four it knows.
    """
    key = outcome.strip()
    return OUTCOME_WORDS.get(key.lower(), key.replace("_", " ").capitalize())


def format_clock_time(micros: int) -> str:
    """``HH:MM:SS`` in UTC, for the cycle feed's time column.

    UTC, never a local zone. The daemon writes microseconds since the epoch and
    the operator may not be sitting in the same zone as the machine; a feed whose
    times silently shift with the viewer's clock cannot be compared against a log.
    """
    return from_micros(micros).strftime("%H:%M:%S")


def format_timestamp(micros: int) -> str:
    """``YYYY-MM-DD HH:MM:SS`` in UTC, for history and the leaderboard.

    History spans days, so the date is part of the value there in a way it is not
    in a feed of the current run's ticks.
    """
    return from_micros(micros).strftime("%Y-%m-%d %H:%M:%S")


def format_rate_pct(value: float | None, *, places: int = PERCENT_PLACES) -> str:
    """A **proportion** rendered as a percentage, deliberately unsigned.

    Rule 2 of ``ui-context.md`` — always explicitly signed — is about *directional*
    values, where a missing sign is a missing direction. A win rate has no
    direction: it runs 0 to 1, and writing ``+62.00%`` would imply a change of
    +62 points against something. So the sign rule does not apply here, and this
    is the only percentage in the console that does not carry one.

    ``float`` is correct here and only here: the leaderboard's metrics are
    statistics, not money. ``None`` renders as an em dash, which reads as absent
    rather than as zero.
    """
    if value is None:
        return ABSENT
    return format(value * 100, "." + str(places) + "f") + "%"


def format_metric(value: float | None, *, places: int = PERCENT_PLACES) -> str:
    """A leaderboard statistic that is not a percentage — Sharpe, deflated Sharpe, Brier.

    ``float`` is correct here for the same reason as :func:`format_rate_pct`: these
    are statistics, never money. A negative one keeps its proper minus sign so the
    column still aligns, and ``None`` reads as absent rather than as zero — an
    unscored model and a model that scored 0.00 are not the same thing.
    """
    if value is None:
        return ABSENT
    return signed(format(value, "." + str(places) + "f"))


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
