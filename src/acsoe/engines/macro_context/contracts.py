"""What engine 6 `macro_context` reads out of ``state``, and what it publishes back.

Every key name this engine reads is a named constant here, with the engine that owns it
beside it — contract rule 3 forbids importing engine 5 to find out what its keys are
called, and a rename upstream without a matching change here would not raise. Engine 6
would simply report every macro asset missing, on every bar, for ever.

The **macro column names** are derived here too, from `modelling.features.FEATURE_NAMES`
and the configured assets, and nothing else builds one. Spec 67's offline dataset builder
joins the same columns out of the archive; if the two spelled a name differently the
predictor would train on `macro_btc_log_return_4` and be handed
`macro_BTC_log_return_4` live, and the artefact's feature-order check is the only thing
that would notice — at load time, as a refusal, with the cause nowhere in the message.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.modelling.features import FEATURE_NAMES

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

#: Every macro column starts with this. One prefix, declared once, so a reader of a
#: training manifest can tell a macro column from a pair's own feature by its name.
MACRO_PREFIX: Final = "macro"


def macro_column(asset: str, feature: str) -> str:
    """The one spelling of a macro column: ``macro_<asset>_<feature>``.

    A function rather than an f-string at each call site, because there are three call
    sites — this engine, the offline dataset builder and the manifest — and two of them
    are in packages that may not import each other.
    """
    return f"{MACRO_PREFIX}_{asset}_{feature}"


def macro_feature_names(assets: Sequence[str]) -> tuple[str, ...]:
    """Every macro column, in a fixed order: assets sorted, features in feature order.

    **Sorted by asset**, deliberately. The configured mapping is a YAML dict and its
    iteration order is the file's, so a reordering of two lines in `config/default.yaml`
    would otherwise permute the trained feature order — and a model handed its columns
    permuted returns confident nonsense with nothing raising.
    """
    return tuple(
        macro_column(asset, feature)
        for asset in sorted(assets)
        for feature in FEATURE_NAMES
    )


def macro_pair_names(configured: Mapping[str, Any], *, spelling: str) -> dict[str, str]:
    """``{asset: pair}`` for one spelling, from whatever the config layer hands back.

    The config model parses `macro` into typed objects; a test double may hand back
    plain dicts. Both are read, because the alternative is an engine that works against
    the real config and not against the criterion driving it, which is the seam this
    project keeps finding on the wrong side.
    """
    out: dict[str, str] = {}
    for asset, pair in configured.items():
        value = pair.get(spelling) if isinstance(pair, Mapping) else getattr(pair, spelling, None)
        if not value:
            raise ValueError(
                f"macro asset {asset!r} has no {spelling!r} pair name. Both spellings "
                "are config, and neither may be inferred from the other: Kraken calls "
                "the same pair BTC/USD live and XBTUSD in the archive."
            )
        out[str(asset)] = str(value)
    return out


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
