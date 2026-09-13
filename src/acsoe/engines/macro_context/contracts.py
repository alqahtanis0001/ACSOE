"""What engine 6 `macro_context` reads out of ``state``, and what it publishes back.

Every key name this engine reads is a named constant here, with the engine that owns it
beside it — contract rule 3 forbids importing engine 5 to find out what its keys are
called, and a rename upstream without a matching change here would not raise. Engine 6
would simply report every macro asset missing, on every bar, for ever.

The **macro column names live in `modelling/macro.py`** and are re-exported here. They were
written in this file first, which was wrong for a reason worth keeping: spec 65 asks that
"the offline builder and the engine cannot disagree about a column name", and the offline
builder is `research/training.py`, which may not import an engine — architecture invariant
5. `modelling/` is the package both sides may import and is where a shared spelling
belongs. The names are still reachable from here, so nothing that reads engine 6's
contracts has to know where they moved. Amended 2026-09-13; spec 65 step 4 records it.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.modelling.macro import (
    MACRO_PREFIX,
    macro_column,
    macro_feature_names,
    macro_pair_names,
)

__all__ = [
    "FEATURE_BAR_TS_FIELD",
    "FEATURE_KEY",
    "FEATURE_NAMES_FIELD",
    "FEATURE_PAIRS_FIELD",
    "FEATURE_ROW_TS_FIELD",
    "KEY_MACRO",
    "MACRO_PREFIX",
    "STATE_KEY",
    "MacroContextState",
    "macro_column",
    "macro_feature_names",
    "macro_pair_names",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "macro_context"

# --------------------------------------------------------------------------- #
# Read from engine 5 `feature` (agent C)
# --------------------------------------------------------------------------- #

FEATURE_KEY: Final = "feature"
FEATURE_PAIRS_FIELD: Final = "pairs"
FEATURE_BAR_TS_FIELD: Final = "bar_ts"
FEATURE_ROW_TS_FIELD: Final = "row_ts"
FEATURE_NAMES_FIELD: Final = "feature_names"

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

#: A mapping of macro asset to its two spellings: ``live`` is what the stream keys
#: candles by, ``archive`` is what the historical file is called. Both come from config
#: and neither is guessed — Kraken's own spellings disagree (``BTC/USD`` live,
#: ``XBTUSD`` in the archive) and a hardcoded either would work in exactly one of the
#: two modes the same code has to run in.
KEY_MACRO: Final = "macro"

#: Re-exported from `modelling/macro.py`, which is where a spelling both the live loop and
#: `research/` must agree on belongs. Kept importable from here so nothing reading engine
#: 6's contracts has to know where the functions live.
__reexported__: Final = (MACRO_PREFIX, macro_column, macro_feature_names, macro_pair_names)


class MacroContextState(BaseModel):
    """The whole of ``state["macro_context"]``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bar_ts: int
    available: bool
    """False when any configured macro asset had no feature row this bar.

    The engine still returns `OK` and still publishes the assets it does have. **What to
    do about a missing context is a judgement for the engines that read it** — engine 8
    will find its feature vector incomplete and block on that, naming the features, which
    is a better message than anything this engine could produce.
    """

    missing: tuple[str, ...] = ()
    """The assets with no row, by asset name rather than by pair, because the asset is
    what a reader recognises and the pair spelling differs between live and archive."""

    assets: tuple[str, ...] = ()
    """Every configured asset, sorted. Published so `missing` can be read as a fraction
    of something rather than as a bare list."""

    pairs: dict[str, str] = {}
    """``{asset: live pair name}``, echoed so a block naming a missing asset can be
    traced to the config line that named the pair."""

    features: dict[str, float | None] = {}
    """``macro_<asset>_<feature>`` to value. **Every configured column is present**, and a
    missing asset's columns are `null` rather than absent or zero.

    Absent would make a downstream feature-order check fail with a shape complaint rather
    than a missing-data one; zero would be a number the model learns from and cannot tell
    from a genuinely flat market.
    """

    def to_state(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
