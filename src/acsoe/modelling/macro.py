"""The macro column names, spelled once for the engine and for the training pipeline.

BTC's and ETH's feature rows travel beside every candidate's own, renamed with a `macro_`
prefix, so a model can tell a 2% move while Bitcoin is up 3% from the same move while
Bitcoin is flat. Engine 6 `macro_context` builds those columns live; spec 67's dataset
builder joins the same columns out of the archive.

**The names live here because `research/` may not import `engines/`.** Architecture
invariant 5: research code never imports from the live loop path. Spec 65 put these
functions in `engines/macro_context/contracts.py` and asked that "the offline builder and
the engine cannot disagree about a column name" — which is the right requirement and the
wrong place to satisfy it from, because the offline builder cannot reach it there. The
alternative that would have happened by default is `research/` growing its own
`f"macro_{asset}_{feature}"`; the two would agree for months, and the first rename would
train a predictor on one spelling and feed it another live, where the only thing that
would object is the artefact's feature-order check — at load time, as a refusal whose
message names the shape and not the cause.

`modelling/` is the package that exists for exactly this, and a column name is part of the
arithmetic that has to agree between live and replay.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from acsoe.modelling.features import FEATURE_NAMES

__all__ = [
    "MACRO_AVAILABLE_COLUMN",
    "MACRO_PREFIX",
    "MacroError",
    "macro_column",
    "macro_feature_names",
    "macro_pair_names",
]


class MacroError(ValueError):
    """A macro configuration that cannot be read, said plainly rather than defaulted."""


#: Every macro column starts with this, so a reader of a training manifest can tell a
#: macro column from a pair's own feature by its name alone.
MACRO_PREFIX: Final = "macro"

#: Whether the macro rows were present for this decision bar. A column rather than a
#: dropped row: a bar where the macro feed was missing is still a bar the pair traded in,
#: and dropping it would silently remove exactly the periods when the feed was broken.
MACRO_AVAILABLE_COLUMN: Final = "macro_available"


def macro_column(asset: str, feature: str) -> str:
    """The one spelling of a macro column: ``macro_<asset>_<feature>``."""
    return f"{MACRO_PREFIX}_{asset}_{feature}"


def macro_feature_names(assets: Sequence[str]) -> tuple[str, ...]:
    """Every macro column, in a fixed order: assets sorted, features in feature order.

    **Sorted by asset**, deliberately. The configured mapping is a YAML dict whose
    iteration order is the file's, so reordering two lines in `config/default.yaml` would
    otherwise permute the trained feature order — and a model handed its columns permuted
    returns confident nonsense with nothing raising.
    """
    return tuple(
        macro_column(asset, feature)
        for asset in sorted(assets)
        for feature in FEATURE_NAMES
    )


def macro_pair_names(configured: Mapping[str, Any], *, spelling: str) -> dict[str, str]:
    """``{asset: pair}`` for one spelling, from whatever the config layer hands back.

    Kraken calls the same market ``BTC/USD`` on the live stream and ``XBTUSD`` in the
    downloadable archive. Neither is derivable from the other, so both are named in
    config; this engine reads ``live`` and the dataset builder reads ``archive``.

    The config model parses `macro` into typed objects and a test double may hand back
    plain dicts. Both are read, because the alternative is code that works against the
    real config and not against the criterion driving it.
    """
    if spelling not in ("live", "archive"):
        raise MacroError(f"{spelling!r} is not a macro pair spelling; use live or archive")
    out: dict[str, str] = {}
    for asset, pair in configured.items():
        value = pair.get(spelling) if isinstance(pair, Mapping) else getattr(pair, spelling, None)
        if not value:
            raise MacroError(
                f"macro asset {asset!r} has no {spelling!r} pair name. Both spellings are "
                "config and neither may be inferred from the other: Kraken calls the same "
                "pair BTC/USD live and XBTUSD in the archive."
            )
        out[str(asset)] = str(value)
    return out
