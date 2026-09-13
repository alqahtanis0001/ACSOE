"""The ``models/<run_id>/`` layout: the manifest, the scaler, and the hash of every file.

One directory per training run, written once and **never overwritten**. Read and written
here and nowhere else, so that the trainer that writes an artefact and the engine that
loads one cannot disagree about what is in it. An engine reaches the directory only
through ``context.clients.store.model_run_dir(run_id)`` and never by building a path —
contract rule 4 — and this module never creates a directory either: it is handed one.

What a manifest has to carry, and why each is not optional:

``feature_names``
    The **ordered** feature list. A model without its exact feature order is unusable:
    hand LightGBM the same columns in a different order and it returns confident
    nonsense with nothing raising. :func:`load_run` refuses a manifest whose feature
    list is not exactly what the caller expects, element by element.
``feature_version``
    Which arithmetic produced those columns. Same names computed a different way is the
    same failure wearing a disguise, and it is the one a name check cannot see.
``config_digest`` and ``seeds``
    A run that cannot be reproduced from its config plus its data is not a result.
``files``
    A sha256 per file in the directory. Verified on load, so a truncated or edited
    artefact is a refusal rather than a model that predicts slightly differently.
``training_identity`` / ``buy_identity``
    Digests over the **identity** of the rows a fold trained on, and of the BUY subset
    inside it. These exist for one criterion: the Dissimilarity Index must be fitted on
    the predictor's training rows and never on the skeptic's BUY subset, and a *count*
    of rows passes whenever the two sets happen to be the same size. Identity is the
    only proof that survives that coincidence.

The scaler is JSON and never a pickle. A pickle in an artefact directory is code that
runs when a model is loaded, and the load happens inside a process that places orders.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MANIFEST_NAME",
    "SCALER_NAME",
    "ArtefactError",
    "FoldBounds",
    "LoadedRun",
    "Manifest",
    "Scaler",
    "identity_digest",
    "load_run",
    "sha256_bytes",
    "sha256_file",
    "write_run",
]

MANIFEST_NAME: Final = "manifest.json"
SCALER_NAME: Final = "scaler.json"

#: Read in blocks rather than whole, because an artefact directory holds model files and
#: this is also how a 400 MB one is hashed on a laptop.
_HASH_BLOCK: Final = 1 << 20


class ArtefactError(ValueError):
    """A refusal to write or to load. Every raise names the file and what was wrong.

    One exception type with several causes, so **every message says which cause** —
    `code-standards.md` records why a bare ``pytest.raises(ArtefactError)`` would be a
    weak assertion here, and the tests match on the message rather than the type.
    """


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_HASH_BLOCK):
            digest.update(block)
    return digest.hexdigest()


def identity_digest(pairs: Sequence[str], decision_ts: Sequence[int]) -> str:
    """A digest over **which rows** a set contains, independent of their order.

    ``(pair, decision_ts)`` identifies a decision bar uniquely across the whole dataset,
    so this is a fingerprint of a *set of rows* and nothing else: not their count, not
    their features, not the order they arrived in. Sorted before hashing so that two
    codepaths producing the same rows in different orders agree.

    This is what `di_fitted_on_predictor_training_set` rests on. A count of rows is the
    weak version of the same check and passes on exactly the folds where most calls are
    BUY, which are the folds a DI fitted on the BUY subset would damage most.
    """
    if len(pairs) != len(decision_ts):
        raise ArtefactError(
            f"identity needs one pair per timestamp; got {len(pairs)} pairs and "
            f"{len(decision_ts)} timestamps"
        )
    rows = sorted(f"{pair}|{int(ts)}" for pair, ts in zip(pairs, decision_ts, strict=True))
    return sha256_bytes("\n".join(rows).encode("utf-8"))


class Scaler(BaseModel):
    """MinMax scaling, as JSON. Fitted on training rows only, never on the test window.

    Fitting on train plus test is a leak that shows up as a slightly better number and
    nothing else. It is in the mutation list for spec 67 for that reason.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_names: tuple[str, ...]
    minimum: tuple[float, ...]
    maximum: tuple[float, ...]

    @classmethod
    def fit(cls, rows: Sequence[Sequence[float]], names: Sequence[str]) -> Scaler:
        if not rows:
            raise ArtefactError("a scaler cannot be fitted on zero rows")
        width = len(names)
        lows = [float("inf")] * width
        highs = [float("-inf")] * width
        for row in rows:
            if len(row) != width:
                raise ArtefactError(
                    f"a row has {len(row)} values against {width} feature names"
                )
            for index, value in enumerate(row):
                number = float(value)
                if number != number:  # NaN carries no information about the range
                    continue
                lows[index] = min(lows[index], number)
                highs[index] = max(highs[index], number)
        for index, name in enumerate(names):
            if lows[index] == float("inf"):
                # Every value of this feature was NaN in the training rows. Scale it to
                # a constant rather than raising: a pair with no history for one window
                # is normal, and refusing the whole fold over it would throw away the
                # features that *are* there.
                lows[index] = 0.0
                highs[index] = 0.0
            del name
        return cls(
            feature_names=tuple(str(name) for name in names),
            minimum=tuple(lows),
            maximum=tuple(highs),
        )

    def transform(self, rows: Iterable[Sequence[float]]) -> list[list[float]]:
        """Scale to ``[0, 1]`` per feature, NaN preserved as NaN.

        A degenerate feature — one whose training minimum and maximum are equal — maps to
        0.5 rather than dividing by zero. Preserving NaN rather than filling it is
        deliberate: LightGBM handles a missing value natively and has learned a split for
        it, and a zero-filled NaN is a value the model was never shown.
        """
        spans = [
            (high - low) if high > low else 0.0
            for low, high in zip(self.minimum, self.maximum, strict=True)
        ]
        out: list[list[float]] = []
        for row in rows:
            if len(row) != len(self.feature_names):
                raise ArtefactError(
                    f"a row has {len(row)} values against "
                    f"{len(self.feature_names)} feature names"
                )
            scaled: list[float] = []
            for index, value in enumerate(row):
                number = float(value)
                if number != number:
                    scaled.append(number)
                elif spans[index] == 0.0:
                    scaled.append(0.5)
                else:
                    scaled.append((number - self.minimum[index]) / spans[index])
            out.append(scaled)
        return out


class FoldBounds(BaseModel):
    """The four timestamps that say what a fold saw, and the counts that say what it lost.

    ``train_end_ts == test_start_ts`` on a past-only walk-forward, and
    ``after_test_count`` is how many rows existed after the test window and were **not**
    trained on. Operator ruling 1 of 2026-09-12: reporting that number is what makes the
    difference between past-only and two-sided visible in a digest rather than only in
    the splitter's source.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fold_index: int
    train_start_ts: int
    train_end_ts: int
    test_start_ts: int
    test_end_ts: int
    train_rows: int
    test_rows: int
    purged_count: int = 0
    embargoed_count: int = 0
    after_test_count: int = 0


class Manifest(BaseModel):
    """Everything needed to say what a model is and to refuse it when it is not that."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    created_at: datetime
    config_digest: str
    seeds: Mapping[str, int]
    feature_version: str
    feature_names: tuple[str, ...]
    class_order: tuple[str, ...]
    fold: FoldBounds
    dataset: Mapping[str, Any] = Field(default_factory=dict)
    metrics: Mapping[str, Any] = Field(default_factory=dict)
    files: Mapping[str, str] = Field(default_factory=dict)
    #: Digest over ``(pair, decision_ts)`` of the fold's training rows, and of the BUY
    #: subset inside them. Both are :func:`identity_digest` output.
    training_identity: str | None = None
    buy_identity: str | None = None
    #: Free-form, and used for the DI and anomaly entries. Never a place for a number a
    #: criterion asserts on without a named field of its own.
    extras: Mapping[str, Any] = Field(default_factory=dict)


class LoadedRun(BaseModel):
    """A verified artefact directory: the manifest, the scaler and where they came from."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    directory: Path
    manifest: Manifest
    scaler: Scaler


def _dump(payload: Mapping[str, Any]) -> bytes:
    """Deterministic JSON bytes.

    Sorted keys and no trailing whitespace, so that two runs over the same config and
    data produce byte-identical manifests and
    `training_is_reproducible_from_config_and_data` can compare bytes rather than
    fields. Written as **bytes**: a bare ``Path.write_text`` on Windows turns every line
    feed into a carriage-return/line-feed pair, and an artefact directory is evidence.
    """
    return json.dumps(payload, sort_keys=True, indent=2, default=str).encode("utf-8") + b"\n"


def write_run(
    directory: Path,
    *,
    manifest: Manifest,
    scaler: Scaler,
) -> Manifest:
    """Write ``manifest.json`` and ``scaler.json`` into an **existing** directory.

    The directory comes from ``StoreClient.new_model_run_dir(run_id)``, which creates it
    and refuses one that already exists. This function never creates a directory and
    never overwrites a manifest: the two refusals live in two places on purpose, because
    the store's is about the run id and this one is about the artefact.

    Every other file — the model, the calibrator, ``di.npz`` — is written by the trainer
    *before* this call and hashed here, so the manifest's ``files`` map describes the
    directory as it actually is. A file present on disk and absent from the map is a
    refusal: an unhashed file in an artefact directory is one nothing would notice being
    swapped.
    """
    if not directory.is_dir():
        raise ArtefactError(
            f"{directory} is not a directory. modelling/artefacts.py never creates one: "
            "the path comes from StoreClient.new_model_run_dir(run_id), which is what "
            "refuses to overwrite an existing run."
        )
    manifest_path = directory / MANIFEST_NAME
    if manifest_path.exists():
        raise ArtefactError(
            f"{manifest_path} already exists. A trained artefact is never overwritten "
            "(code-standards.md, Models); write a new run id."
        )

    scaler_path = directory / SCALER_NAME
    scaler_path.write_bytes(_dump(scaler.model_dump(mode="json")))

    hashed = {
        path.name: sha256_file(path)
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != MANIFEST_NAME
    }
    complete = manifest.model_copy(update={"files": hashed})
    manifest_path.write_bytes(_dump(complete.model_dump(mode="json")))
    return complete


def load_run(
    directory: Path,
    *,
    expected_features: Sequence[str],
    expected_version: str | None = None,
) -> LoadedRun:
    """Read an artefact directory, verifying every hash and the exact feature order.

    :param expected_features: the feature list the caller computes, in the order it
        computes it. Engine 8 passes ``FEATURE_NAMES`` plus the macro columns; engine 13
        passes ``MARKET_QUALITY_FEATURES``. It is a parameter rather than a constant
        because the three engines legitimately expect three different lists, and an
        artefact that agrees with the wrong one of them is exactly the failure to catch.

    Refuses, each with its own message:

    * a missing ``manifest.json`` or ``scaler.json`` — a fresh clone has no ``models/``
      at all, and the engines block on that rather than the process refusing to start;
    * a file whose sha256 does not match the manifest;
    * a file on disk that the manifest does not hash;
    * a feature list that differs from ``expected_features`` in content **or order**;
    * a ``feature_version`` other than ``expected_version`` when one is given.
    """
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ArtefactError(
            f"{manifest_path} does not exist. A fresh clone has no models/ and the "
            "engine that asked for this run must block rather than predict."
        )
    try:
        payload = json.loads(manifest_path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtefactError(f"{manifest_path} is not readable JSON: {exc}") from exc
    manifest = Manifest.model_validate(payload)

    on_disk = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name != MANIFEST_NAME
    }
    unhashed = sorted(on_disk - set(manifest.files))
    if unhashed:
        raise ArtefactError(
            f"{directory} holds files the manifest does not hash: "
            + ", ".join(unhashed)
            + ". An unhashed file in an artefact directory is one nothing would notice "
            "being swapped."
        )
    for name, expected_hash in sorted(manifest.files.items()):
        path = directory / name
        if not path.is_file():
            raise ArtefactError(f"{path} is named in the manifest and is not on disk")
        actual = sha256_file(path)
        if actual != expected_hash:
            raise ArtefactError(
                f"{path} has sha256 {actual}, the manifest says {expected_hash}. The "
                "artefact has changed since it was written; refusing to load it."
            )

    scaler_path = directory / SCALER_NAME
    if not scaler_path.is_file():
        raise ArtefactError(f"{scaler_path} does not exist")
    scaler = Scaler.model_validate(json.loads(scaler_path.read_bytes().decode("utf-8")))

    wanted = tuple(str(name) for name in expected_features)
    if manifest.feature_names != wanted:
        raise ArtefactError(
            _order_complaint(manifest.feature_names, wanted, str(manifest_path))
        )
    if scaler.feature_names != wanted:
        raise ArtefactError(
            _order_complaint(scaler.feature_names, wanted, str(scaler_path))
        )
    if expected_version is not None and manifest.feature_version != expected_version:
        raise ArtefactError(
            f"{manifest_path} was written at feature_version "
            f"{manifest.feature_version!r} and this process computes "
            f"{expected_version!r}. The same names computed a different way is a model "
            "being handed inputs it has never seen, and a name check cannot see it."
        )
    return LoadedRun(directory=directory, manifest=manifest, scaler=scaler)


def _order_complaint(found: Sequence[str], wanted: Sequence[str], where: str) -> str:
    """Say whether the list is a different *set* or the same set in a different order.

    The two are different faults with different fixes and they are trivially
    distinguishable, so the message distinguishes them. A permuted list is the dangerous
    one: every name is present, nothing looks wrong, and the model is being fed its
    columns shuffled.
    """
    if sorted(found) == sorted(wanted):
        first = next(
            (i for i, (a, b) in enumerate(zip(found, wanted, strict=False)) if a != b),
            0,
        )
        return (
            f"{where} carries the right {len(wanted)} features in the wrong ORDER: "
            f"position {first} is {found[first]!r} where this process computes "
            f"{wanted[first]!r}. A model handed its columns permuted returns confident "
            "nonsense and nothing raises."
        )
    missing = sorted(set(wanted) - set(found))
    extra = sorted(set(found) - set(wanted))
    return (
        f"{where} carries {len(found)} features against the {len(wanted)} this process "
        "computes"
        + (f"; missing {', '.join(missing)}" if missing else "")
        + (f"; unexpected {', '.join(extra)}" if extra else "")
    )
