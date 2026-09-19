"""The one package both the live loop and `research/` import.

Architecture invariant 5 keeps the two sides apart: the live loop never imports
`research/` and `research/` never imports the live loop. The obvious consequence of
that rule — two implementations of the same indicator, drifting apart — is the defect
that makes a backtest meaningless while every test stays green, because each
implementation is tested against itself and nothing ever compares them.

`modelling/` is the exception the operator ruled on 2026-09-12, and it is a **leaf**:

* it imports nothing from `acsoe` except types in `core/contracts.py`;
* it reads no ``state``, opens no client, holds no engine and never touches the clock;
* every input is an argument.

A test walks its import graph to keep it that way. If something here needs a client or
the clock, the thing that needs it belongs in an engine or in `research/`, not here.

What lives here is exactly the arithmetic that has to **agree** between live and replay:

============================  ==========================================================
:mod:`~acsoe.modelling.features`     the feature vector, computed once for engine 5 and
                                     for the training pipeline
:mod:`~acsoe.modelling.weights`      average-uniqueness sample weights and the effective
                                     sample size reported beside every row count
:mod:`~acsoe.modelling.artefacts`    the ``models/<run_id>/`` layout: the manifest, the
                                     scaler and the per-file hashes an engine verifies
:mod:`~acsoe.modelling.di`           the Dissimilarity Index, fitted by the trainer and
                                     scored by engine 8
:mod:`~acsoe.modelling.expected_move` the expected move a BUY call is decided on, and
                                     which engine 10 prices against friction
:mod:`~acsoe.modelling.ranking`      engine 7's order by expected move, skipping every
                                     pair engines 13 and 8 would refuse (spec 144)
============================  ==========================================================

Nothing here is imported for its side effects and nothing loads a model at import time.
"""

from __future__ import annotations

__all__ = [
    "artefacts",
    "calibration",
    "di",
    "expected_move",
    "features",
    "macro",
    "ranking",
    "weights",
]
