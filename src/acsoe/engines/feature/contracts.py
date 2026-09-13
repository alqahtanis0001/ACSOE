"""What engine 5 `feature` reads out of ``state``, and what it publishes back into it.

**Every key name this engine reads lives here and nowhere else**, with the engine that
owns it written beside it. Contract rule 3 forbids importing another engine to find out
what its keys are called, and a key renamed upstream without a matching change here does
not raise — engine 5 would simply publish nothing, on every tick, silently. That is the
pattern `engines/memory/contracts.py` set and the reason it exists.

``state["feature"]["pairs"][pair]`` is a **cross-chain key**, fixed in
`context/engine-contracts.md`: engine 7 `scout` (B) ranks on it, and engines 6, 8, 12 and
13 read it. Its shape may not be changed without the lead.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "BAR_CLOSED_FIELD",
    "CANDLES_FIELD",
    "CANDLE_MONEY_FIELDS",
    "CANDLE_PAIR_FIELD",
    "CANDLE_TRADES_FIELD",
    "CANDLE_TS_FIELD",
    "CLOSED_BAR_TS_FIELD",
    "INTERVAL_FIELD",
    "KEY_MAX_LOOKBACK_BARS",
    "KEY_MIN_LOOKBACK_FILL",
    "MARKET_SENSOR_KEY",
    "STATE_KEY",
    "FeatureState",
    "MissingInputError",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "feature"

# --------------------------------------------------------------------------- #
# Read from engine 3 `market_sensor` (agent A)
# --------------------------------------------------------------------------- #

MARKET_SENSOR_KEY: Final = "market_sensor"

#: True only on the tick where a 15-minute decision bar completed. Engine 5 returns
#: `PASS` when it is false and the opportunity chain stops there — that is the cadence
#: mechanism in `engine-contracts.md`, and **no other engine may infer the bar boundary
#: for itself**.
BAR_CLOSED_FIELD: Final = "bar_closed"

#: The opening second of the bar that just closed.
CLOSED_BAR_TS_FIELD: Final = "closed_bar_ts"

#: The decision-bar grid engine 3 actually used. Read from ``state`` rather than from
#: `timeframes.decision_bar_s`, deliberately: engine 3 built the candles on this grid,
#: and two readers of one config key can still disagree if one of them is stale, while a
#: value that travels with the data cannot.
INTERVAL_FIELD: Final = "interval_s"

#: Closed candles only, oldest first, money as exact decimal strings. **The in-progress
#: bar is never here** — engine 3 does not publish it, and engine 5 filters to
#: ``ts <= closed_bar_ts`` anyway rather than trusting that.
CANDLES_FIELD: Final = "candles"

CANDLE_PAIR_FIELD: Final = "pair"
CANDLE_TS_FIELD: Final = "ts"
CANDLE_TRADES_FIELD: Final = "trades"

#: The candle fields that arrive as decimal strings and become floats. **This is the one
#: place in the system where that conversion happens on the live path.** Features are
#: model inputs, not money — `code-standards.md` puts float and numpy on this side of the
#: line — and doing it here, once, is what lets the offline builder cast from the
#: archive's `Decimal` columns and get the same doubles.
CANDLE_MONEY_FIELDS: Final[tuple[str, ...]] = ("open", "high", "low", "close", "volume")

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

#: The fraction of a lookback window that must be filled before its features are a
#: number rather than NaN. No default: `Config.get` raises on an absent key, the
#: orchestrator turns that into `ERROR`, and that is the honest answer for a threshold
#: nobody has set.
KEY_MIN_LOOKBACK_FILL: Final = "features.min_lookback_fill"

#: The configured ceiling on how far back a feature may look. Checked against
#: `modelling.features.MAX_LOOKBACK_BARS` on every tick, because the two drifting apart
#: is invisible: the offline builder would fill the longest window over the archive while
#: the live path never could, and the two paths would differ on every bar with the
#: offline number being the one that looks right.
KEY_MAX_LOOKBACK_BARS: Final = "features.max_lookback_bars"


class MissingInputError(ValueError):
    """A ``state`` shape engine 3 cannot actually produce.

    Raised rather than worked around. The orchestrator turns it into `ERROR`, which
    blocks — the correct answer when the engine that owns the decision-bar clock has
    published something this engine cannot read, because every alternative involves
    guessing at what the market did.
    """


class FeatureState(BaseModel):
    """The whole of ``state["feature"]``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bar_ts: int
    """The decision bar that closed on this tick. One number for the whole payload."""

    interval_s: int

    feature_version: str
    """`modelling.features.FEATURE_VERSION`. An artefact records the version it was
    trained at and engine 8 refuses one that disagrees, so it travels with every row."""

    feature_names: tuple[str, ...]
    """`modelling.features.FEATURE_NAMES`, in order. Published so that a consumer never
    has to import the modelling package to know what the values mean, and so that a
    reader can see the order the artefacts are held to."""

    pairs: dict[str, dict[str, float | None]] = {}
    """One row per pair engine 3 published candles for. **Floats and `null`, never NaN**:
    ``state`` must be JSON-serialisable (contract rule 8) and a float NaN is not. `null`
    means "not computable from the bars that were there" and never zero."""

    row_ts: dict[str, int] = {}
    """The bar each pair's row actually describes.

    Normally `bar_ts` for every pair. It differs when a pair had **no trades** in the
    decision bar: the archive and the live stream both simply have no candle there, and
    inventing one is forbidden. Rather than dropping the pair or publishing a row dated
    to a bar it has no data for, the row is the pair's most recent closed bar at or
    before `bar_ts` and this says which. A consumer that cares about staleness compares
    the two; one that does not is unaffected.
    """

    pairs_with_short_history: tuple[str, ...] = ()
    """Pairs whose candles do not cover the longest lookback window.

    **Published with null features and listed, never dropped.** Engine 7 must be able to
    see that a pair was considered and could not be judged, which is a different fact
    from a pair that was never looked at.
    """

    gaps_in_range: dict[str, int] = {}
    """Per pair, how many bar slots inside its own covered range hold no candle.

    A hole means no trades occurred; nothing is interpolated. Counted **per pair from
    that pair's own candles**, and not read through from engine 3's `missing_bars`,
    which is computed over every pair's timestamps pooled together — a slot is only
    absent from that union when *no pair anywhere* traded in it, so on a multi-pair tick
    it reports nearly nothing and would report it identically for every pair.
    """

    def to_state(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
