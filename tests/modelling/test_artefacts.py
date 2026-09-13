"""`models/<run_id>/` — the manifest, the JSON scaler, and a hash per file.

Spec 63's fourth named mutation is **the manifest loader accepting a feature list in a
different order**, and it is the one this module is built around. It is worth stating
why it is dangerous rather than merely wrong: a permuted list has every expected name
present, so a set comparison passes, a count passes, and a human reading the manifest
sees nothing odd. The model is then handed its columns shuffled and returns confident
nonsense, and the only place that could have objected is this loader.

`code-standards.md` is why every refusal here is matched on its **message**:
`ArtefactError` has one type and several causes, so `pytest.raises(ArtefactError)` alone
cannot tell the failure a test induced from one that happened first.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.conftest import require_module

artefacts = require_module(
    "acsoe.modelling.artefacts", reason="acsoe.modelling.artefacts does not exist yet"
)

NAMES = ("alpha", "beta", "gamma")
CLASS_ORDER = ("target", "stop", "timeout")


def a_scaler() -> object:
    return artefacts.Scaler.fit([[0.0, 10.0, -1.0], [2.0, 30.0, 1.0]], NAMES)


def a_manifest(**overrides: object) -> object:
    base = {
        "run_id": "train-20260913-abcdef-f0",
        "created_at": datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
        "config_digest": "0" * 64,
        "seeds": {"train": 20260908, "global": 20260908},
        "feature_version": "f1",
        "feature_names": NAMES,
        "class_order": CLASS_ORDER,
        "fold": artefacts.FoldBounds(
            fold_index=0,
            train_start_ts=1_000_000,
            train_end_ts=2_000_000,
            test_start_ts=2_000_000,
            test_end_ts=2_600_000,
            train_rows=500,
            test_rows=60,
        ),
    }
    base.update(overrides)
    return artefacts.Manifest(**base)


def a_run(root: Path, *, name: str = "run-1") -> Path:
    directory = root / name
    directory.mkdir()
    (directory / "model.txt").write_bytes(b"tree 0\n")
    artefacts.write_run(directory, manifest=a_manifest(), scaler=a_scaler())
    return directory


# --------------------------------------------------------------------------- #
# The feature order
# --------------------------------------------------------------------------- #


def test_a_run_loads_when_the_feature_order_matches_exactly(tmp_path: Path) -> None:
    loaded = artefacts.load_run(a_run(tmp_path), expected_features=NAMES, expected_version="f1")
    assert loaded.manifest.feature_names == NAMES
    assert loaded.scaler.feature_names == NAMES


def test_a_permuted_feature_list_is_refused_and_named_as_an_ordering_problem(
    tmp_path: Path,
) -> None:
    """The mutation, and the message has to distinguish it from a different *set*.

    Both are refusals; only one of them is a shuffle, and a reader who is told "3
    features against 3" learns nothing about which. The message names the first position
    that differs.

    **This test alone is not enough**, and the two below say why: `load_run` checks the
    order twice, once against the manifest and once against the scaler, and with the
    caller passing a permuted list both branches fire. A mutation of either one is caught
    by the other, so each needs a test that can only reach it.
    """
    directory = a_run(tmp_path)
    permuted = (NAMES[1], NAMES[0], NAMES[2])
    with pytest.raises(artefacts.ArtefactError, match="wrong ORDER"):
        artefacts.load_run(directory, expected_features=permuted)


def test_a_manifest_whose_order_is_wrong_is_refused_even_when_the_scaler_is_right(
    tmp_path: Path,
) -> None:
    """The manifest branch, reached on its own. Spec 63's fourth named mutation.

    Found by mutation: weakening `manifest.feature_names != wanted` to a sorted
    comparison **survived the whole suite**, because the test above reached the scaler's
    identical check a few lines later and matched the same message. The manifest branch
    read as covered in every sweep and was covered by nobody.

    It is the branch that matters more. The scaler is a file the manifest hashes, so it
    can only disagree with the manifest if both were written wrong together; the
    manifest's list is the one an **engine** is held to, and engines 8 and 13 pass two
    different expected lists to this loader.

    Reachable because `manifest.json` is deliberately not hashed by itself, so it can
    carry a permuted list without the hash check firing first.
    """
    directory = tmp_path / "permuted-manifest"
    directory.mkdir()
    (directory / "model.txt").write_bytes(b"tree 0\n")
    permuted = (NAMES[1], NAMES[0], NAMES[2])
    artefacts.write_run(
        directory, manifest=a_manifest(feature_names=permuted), scaler=a_scaler()
    )

    with pytest.raises(artefacts.ArtefactError) as raised:
        artefacts.load_run(directory, expected_features=NAMES)
    message = str(raised.value)
    assert "wrong ORDER" in message
    assert artefacts.MANIFEST_NAME in message, (
        "the refusal must name the manifest, or it is indistinguishable from the "
        "scaler's identical check and either one can stand in for the other"
    )


def test_a_scaler_whose_order_is_wrong_is_refused_even_when_the_manifest_is_right(
    tmp_path: Path,
) -> None:
    """The scaler branch, reached on its own — the mirror of the test above.

    Built by writing the run with a permuted scaler, so the manifest hashes that file
    correctly and the hash check passes. The order check is then the only thing left that
    can refuse it.
    """
    directory = tmp_path / "permuted-scaler"
    directory.mkdir()
    (directory / "model.txt").write_bytes(b"tree 0\n")
    permuted_scaler = artefacts.Scaler.fit(
        [[0.0, 10.0, -1.0], [2.0, 30.0, 1.0]], (NAMES[1], NAMES[0], NAMES[2])
    )
    artefacts.write_run(directory, manifest=a_manifest(), scaler=permuted_scaler)

    with pytest.raises(artefacts.ArtefactError) as raised:
        artefacts.load_run(directory, expected_features=NAMES)
    message = str(raised.value)
    assert "wrong ORDER" in message
    assert artefacts.SCALER_NAME in message


def test_a_different_feature_set_is_refused_and_says_which_names(tmp_path: Path) -> None:
    directory = a_run(tmp_path)
    with pytest.raises(artefacts.ArtefactError, match="missing delta"):
        artefacts.load_run(directory, expected_features=(*NAMES, "delta"))


def test_the_scaler_is_checked_against_the_same_order_as_the_manifest(
    tmp_path: Path,
) -> None:
    """A manifest and a scaler disagreeing about the order is the same defect one file
    over, and it is reachable by editing either. Both are checked."""
    directory = a_run(tmp_path)
    scaler_path = directory / artefacts.SCALER_NAME
    payload = json.loads(scaler_path.read_bytes().decode("utf-8"))
    payload["feature_names"] = [NAMES[2], NAMES[1], NAMES[0]]
    scaler_path.write_bytes(json.dumps(payload).encode("utf-8"))
    # The manifest's own hash of scaler.json now fails first, which is correct and is
    # itself the point: the hash is what stops a file being edited underneath a loader.
    with pytest.raises(artefacts.ArtefactError, match="has sha256"):
        artefacts.load_run(directory, expected_features=NAMES)


def test_a_feature_version_mismatch_is_refused(tmp_path: Path) -> None:
    """The same names computed a different way. A name check cannot see it, which is
    why the version exists at all."""
    directory = a_run(tmp_path)
    with pytest.raises(artefacts.ArtefactError, match="feature_version"):
        artefacts.load_run(directory, expected_features=NAMES, expected_version="f2")


# --------------------------------------------------------------------------- #
# Hashes and overwriting
# --------------------------------------------------------------------------- #


def test_every_file_in_the_directory_is_hashed(tmp_path: Path) -> None:
    directory = a_run(tmp_path)
    manifest = json.loads((directory / artefacts.MANIFEST_NAME).read_bytes().decode("utf-8"))
    assert set(manifest["files"]) == {"model.txt", artefacts.SCALER_NAME}
    assert all(len(value) == 64 for value in manifest["files"].values())


def test_an_edited_artefact_is_refused(tmp_path: Path) -> None:
    directory = a_run(tmp_path)
    (directory / "model.txt").write_bytes(b"tree 1\n")
    with pytest.raises(artefacts.ArtefactError, match="has sha256"):
        artefacts.load_run(directory, expected_features=NAMES)


def test_an_unhashed_file_appearing_later_is_refused(tmp_path: Path) -> None:
    """A file the manifest does not mention is one nothing would notice being swapped.
    Refusing is the fail-closed reading, and it is also how a half-written run — model
    on disk, manifest from an earlier attempt — is caught."""
    directory = a_run(tmp_path)
    (directory / "calibrator.json").write_bytes(b"{}\n")
    with pytest.raises(artefacts.ArtefactError, match="does not hash"):
        artefacts.load_run(directory, expected_features=NAMES)


def test_writing_twice_into_one_run_is_refused(tmp_path: Path) -> None:
    """A trained artefact is never overwritten. The store refuses the run id and this
    refuses the manifest; two refusals in two places, because they are about two
    different things and either one alone leaves a way through."""
    directory = a_run(tmp_path)
    with pytest.raises(artefacts.ArtefactError, match="already exists"):
        artefacts.write_run(directory, manifest=a_manifest(), scaler=a_scaler())


def test_this_module_never_creates_the_directory(tmp_path: Path) -> None:
    """The path comes from `StoreClient.new_model_run_dir(run_id)`, which is what
    refuses an existing run. A module that created its own directory would route around
    that refusal without anybody deciding to."""
    absent = tmp_path / "never-made"
    with pytest.raises(artefacts.ArtefactError, match="is not a directory"):
        artefacts.write_run(absent, manifest=a_manifest(), scaler=a_scaler())
    assert not absent.exists()


def test_a_missing_manifest_is_refused_with_the_fresh_clone_named(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(artefacts.ArtefactError, match="does not exist"):
        artefacts.load_run(empty, expected_features=NAMES)


def test_the_scaler_is_json_and_not_a_pickle(tmp_path: Path) -> None:
    """A pickle in an artefact directory is code that runs when a model is loaded, and
    the load happens inside the process that places orders."""
    directory = a_run(tmp_path)
    payload = json.loads((directory / artefacts.SCALER_NAME).read_bytes().decode("utf-8"))
    assert set(payload) == {"feature_names", "minimum", "maximum"}


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #


def test_identity_is_about_which_rows_not_how_many_or_in_what_order() -> None:
    """The property `di_fitted_on_predictor_training_set` rests on.

    Order must not matter, because two codepaths producing the same rows in different
    orders have produced the same set. Content must matter, because the whole check is
    "which rows did the DI see", and a digest that moved with the count alone would pass
    on exactly the folds where the training set and the BUY subset are the same size.
    """
    one = artefacts.identity_digest(["AAA", "BBB"], [900, 1800])
    reordered = artefacts.identity_digest(["BBB", "AAA"], [1800, 900])
    different = artefacts.identity_digest(["AAA", "BBB"], [900, 2700])
    same_count = artefacts.identity_digest(["CCC", "DDD"], [900, 1800])

    assert one == reordered
    assert one != different
    assert one != same_count


def test_identity_refuses_mismatched_columns() -> None:
    with pytest.raises(artefacts.ArtefactError, match="one pair per timestamp"):
        artefacts.identity_digest(["AAA"], [900, 1800])


def test_a_subset_is_detectable_from_the_entries_rather_than_from_the_digest() -> None:
    """Stated as a test because it is the thing a reader will assume is false.

    A digest proves *equality* of two sets and can never prove *containment*: that is
    why `modelling/di.py` stores the reference set's entries in `di.npz` rather than only
    a hash of them. This test pins the reasoning so that a later simplification to
    "store the hash, it is smaller" meets an assertion instead of a blank page.
    """
    training = ["AAA|900", "AAA|1800", "BBB|900"]
    reference = ["AAA|900", "BBB|900"]
    assert set(reference) <= set(training)
    assert artefacts.identity_digest(
        [e.split("|")[0] for e in reference], [int(e.split("|")[1]) for e in reference]
    ) != artefacts.identity_digest(
        [e.split("|")[0] for e in training], [int(e.split("|")[1]) for e in training]
    )


# --------------------------------------------------------------------------- #
# The scaler
# --------------------------------------------------------------------------- #


def test_the_scaler_maps_the_training_range_onto_zero_to_one() -> None:
    scaler = a_scaler()
    assert scaler.transform([[0.0, 10.0, -1.0]]) == [[0.0, 0.0, 0.0]]
    assert scaler.transform([[2.0, 30.0, 1.0]]) == [[1.0, 1.0, 1.0]]
    assert scaler.transform([[1.0, 20.0, 0.0]]) == [[0.5, 0.5, 0.5]]


def test_nan_survives_scaling_rather_than_becoming_a_number() -> None:
    """LightGBM handles a missing value natively and has learned a split for it. A
    zero-filled NaN is a value the model was never shown, and it is indistinguishable
    downstream from a genuine zero."""
    scaled = a_scaler().transform([[float("nan"), 20.0, 0.0]])[0]
    assert scaled[0] != scaled[0]
    assert scaled[1] == 0.5


def test_a_constant_feature_scales_to_a_half_rather_than_dividing_by_zero() -> None:
    scaler = artefacts.Scaler.fit([[5.0], [5.0]], ("flat",))
    assert scaler.transform([[5.0], [9.0]]) == [[0.5], [0.5]]


def test_a_narrowed_scaler_scales_its_columns_exactly_as_the_wide_one_did() -> None:
    """The property engine 13 and the anomaly trainer both depend on.

    Engine 13 reads only `MARKET_QUALITY_FEATURES` and has no macro columns to build a full
    vector from, so it narrows the scaler; the trainer fits on the same narrowed one. If
    narrowing changed a single bound by a bit, the offline threshold and the live score
    would be measured in different units — and the refusal rate would move for a reason
    nobody could name, with no error anywhere.
    """
    scaler = a_scaler()
    wide = scaler.transform([[0.4, 17.0, 0.25]])[0]
    narrow = scaler.subset(("gamma", "alpha")).transform([[0.25, 0.4]])[0]
    assert narrow == [wide[2], wide[0]]


def test_a_narrowed_scaler_keeps_the_order_it_was_asked_for() -> None:
    """Not the order the wide scaler happened to be fitted in. The caller's order is the
    order its own vector is built in, and a narrowing that silently re-sorted would put
    every value in the wrong column with every value still in range."""
    narrowed = a_scaler().subset(("gamma", "alpha"))
    assert narrowed.feature_names == ("gamma", "alpha")


def test_narrowing_to_a_name_the_scaler_never_saw_is_refused() -> None:
    """Dropped silently, a live vector would be one feature short of the fit and every
    value after the gap would be read as the wrong feature."""
    with pytest.raises(artefacts.ArtefactError, match="delta"):
        a_scaler().subset(("alpha", "delta"))


def test_a_scaler_cannot_be_fitted_on_nothing() -> None:
    with pytest.raises(artefacts.ArtefactError, match="zero rows"):
        artefacts.Scaler.fit([], NAMES)


def test_a_row_of_the_wrong_width_is_refused() -> None:
    with pytest.raises(artefacts.ArtefactError, match="against 3 feature names"):
        artefacts.Scaler.fit([[1.0, 2.0]], NAMES)


def test_the_manifest_json_is_deterministic(tmp_path: Path) -> None:
    """Two runs over the same config and data must produce byte-identical manifests, or
    `training_is_reproducible_from_config_and_data` has to compare fields one at a time
    and will miss whichever one nobody thought of."""
    first = a_run(tmp_path, name="one")
    second = a_run(tmp_path, name="two")
    assert (first / artefacts.MANIFEST_NAME).read_bytes() == (
        second / artefacts.MANIFEST_NAME
    ).read_bytes()
