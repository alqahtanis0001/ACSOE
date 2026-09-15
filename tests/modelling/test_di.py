"""The Dissimilarity Index arithmetic: leave-one-out, identity, and fail-closed on NaN.

Spec 68 exists on its own because the wrong version of this is invisible. Fitted on the
skeptic's BUY subset the DI learns that "normal" means a BUY-shaped setup and then
vetoes every ordinary market state: the veto rate is high, the few trades that survive
look clean, and the leaderboard flatters the model. Nothing crashes and no test goes red.

Two of these tests are the ones that matter:

* :func:`test_a_fit_on_a_tight_cluster_refuses_an_ordinary_row_the_broad_fit_accepts` is
  the defect, constructed. It is the case spec 68 asks for in as many words, and it shows
  that the two fits genuinely disagree about an ordinary row rather than merely being
  fitted on different numbers of rows.
* :func:`test_leaving_the_row_out_is_what_keeps_the_threshold_where_the_live_scores_land`
  is the subtler one: scoring a reference row against a set containing it finds itself at
  distance zero, which drags the whole distribution down and puts the threshold below
  where live scores will fall. The veto then almost never fires, which looks exactly like
  a well-behaved model.

And one the ruling of 2026-09-15 added, because leaving out the row alone was the same
defect one step removed:
:func:`test_same_moment_rows_on_other_pairs_are_left_out_of_the_distribution`. Most DI
columns are macro and calendar features identical for every pair on one bar, so a row's
nearest neighbours were its own moment's rows and the threshold measured time proximity.
The fit leaves out every reference row within the exclusion span, across pairs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import require_module

np = require_module("numpy", reason="numpy is not installed")
di = require_module("acsoe.modelling.di", reason="acsoe.modelling.di does not exist yet")

NEIGHBOURS = 5
PERCENTILE = 0.95
BAR_S = 900
#: `backtest.embargo_bars x timeframes.decision_bar_s` as committed. Spelled here rather
#: than read from config because this module is the arithmetic; the trainer's tests prove
#: the trainer reads the real one.
SPAN_S = 48 * BAR_S


def cloud(rows: int, *, spread: float, seed: int, width: int = 4) -> object:
    rng = np.random.default_rng(seed)
    return rng.normal(scale=spread, size=(rows, width))


def identity(rows: int, *, pair: str = "AAAUSD") -> list[str]:
    return [f"{pair}|{BAR_S * index}" for index in range(rows)]


def stamps(rows: int) -> list[int]:
    """The `decision_ts` half of :func:`identity`, one bar apart."""
    return [BAR_S * index for index in range(rows)]


def fit_on(reference: object, rows: int, **overrides: object) -> object:
    arguments: dict[str, object] = {
        "neighbours": NEIGHBOURS,
        "percentile": PERCENTILE,
        "decision_ts": stamps(rows),
        "exclusion_s": SPAN_S,
    }
    arguments.update(overrides)
    return di.fit(reference, identity(rows), **arguments)


def a_fit(rows: int = 300, *, spread: float = 1.0, seed: int = 7) -> object:
    return fit_on(cloud(rows, spread=spread, seed=seed), rows)


def brute_force_distribution(
    reference: object, decision_ts: object, *, neighbours: int, span_s: int | None
) -> object:
    """The leave-one-out statistic from the full distance matrix, written independently.

    `span_s=None` leaves out the row alone - the reading before 2026-09-15, kept here only
    as the comparison the defect is measured against.
    """
    matrix = np.asarray(reference, dtype=np.float64)
    ts = np.asarray(decision_ts, dtype=np.int64)
    distances = np.sqrt(((matrix[:, None, :] - matrix[None, :, :]) ** 2).sum(axis=2))
    np.fill_diagonal(distances, np.inf)
    if span_s is not None:
        distances[np.abs(ts[:, None] - ts[None, :]) <= span_s] = np.inf
    return np.sort(distances, axis=1)[:, :neighbours].mean(axis=1)


# --------------------------------------------------------------------------- #
# What the fit is
# --------------------------------------------------------------------------- #


def test_a_fit_records_the_identity_of_every_reference_row() -> None:
    """Not a count. A count passes whenever two sets happen to be the same size, and on
    a fold where most calls are BUY the training set and the BUY subset usually are."""
    fitted = a_fit(120)
    assert len(fitted.identity) == fitted.rows == 120
    assert fitted.identity[0] == "AAAUSD|0"
    assert len(set(fitted.identity)) == 120


def test_the_threshold_sits_at_the_configured_percentile_of_the_distribution() -> None:
    fitted = a_fit(400)
    above = int((fitted.distribution > fitted.threshold).sum())
    # A 95th percentile over 400 rows leaves about 20 above it. Asserted as a band
    # rather than a number because the quantile interpolates, and asserted at all
    # because a threshold taken from the wrong end of the distribution refuses almost
    # everything or almost nothing and both look plausible in isolation.
    assert 10 <= above <= 30, above


def test_an_ordinary_row_is_accepted_and_a_distant_one_is_refused() -> None:
    fitted = a_fit(300)
    ordinary = di.score(fitted, fitted.reference[0])
    distant = di.score(fitted, np.full(fitted.width, 50.0))
    assert not ordinary.refused
    assert distant.refused
    assert distant.di > ordinary.di


def test_a_row_exactly_on_the_threshold_is_accepted() -> None:
    """The threshold is the last acceptable value, not the first refused one — the same
    direction every other comparison in this system rounds. Pinned because flipping it
    is a one-character change that no metric would ever reveal."""
    fitted = a_fit(200)
    score = di.DiScore(di=fitted.threshold, threshold=fitted.threshold, refused=False)
    assert not score.refused
    # And the real path agrees at the boundary.
    assert not di.score(fitted, fitted.reference[0]).refused


# --------------------------------------------------------------------------- #
# The two defects this module exists to prevent
# --------------------------------------------------------------------------- #


def test_a_fit_on_a_tight_cluster_refuses_an_ordinary_row_the_broad_fit_accepts() -> None:
    """Spec 68's constructed case: the BUY subset is a tight cluster, the training set
    is not, and the two fits disagree about a perfectly ordinary market state.

    This is what "fitted on the wrong rows" costs, made visible. Both fits are valid
    arithmetic over their own inputs; only the rows differ, and only one of them is the
    predictor's training set.
    """
    # The BUY subset is a **subset of the training rows**, not a separate population —
    # that is what makes the two fits comparable and the defect reachable by a one-line
    # mistake in the trainer rather than by handing the fit a different dataset.
    tight = cloud(120, spread=0.15, seed=11)
    rest = cloud(380, spread=1.5, seed=12)
    broad = np.vstack([tight, rest])

    broad_fit = fit_on(broad, broad.shape[0])
    tight_fit = fit_on(tight, tight.shape[0])

    # An ordinary row: an unremarkable member of the broad training set, far outside the
    # tight cluster. Taken from the training set itself, so no row is being invented.
    ordinary = next(row for row in rest if 1.0 < float(np.abs(row).max()) < 2.0)

    assert not di.score(broad_fit, ordinary).refused, (
        "the correctly fitted DI must accept an ordinary row from its own training set"
    )
    assert di.score(tight_fit, ordinary).refused, (
        "the DI fitted on the tight subset must refuse it — this is the failure that "
        "produces a high veto rate, a handful of clean-looking trades and a flattering "
        "leaderboard, with nothing going red"
    )


def test_leaving_the_row_out_is_what_keeps_the_threshold_where_the_live_scores_land() -> None:
    """Scoring a reference row against a set containing it finds itself at zero.

    With `k = 5` that pulls one of the five distances to zero and lowers every statistic
    by about a fifth, so the threshold lands below where live scores fall and the veto
    almost never fires. The comparison here is between the leave-one-out distribution the
    fit computes and the self-inclusive statistic, over the same rows.
    """
    fitted = a_fit(300)
    self_inclusive = np.array(
        [di.score(fitted, row).di for row in fitted.reference[:100]]
    )
    loo = fitted.distribution[:100]
    assert float(self_inclusive.mean()) < float(loo.mean()), (
        "a self-inclusive statistic must be the smaller one; if it is not, the fit is "
        "not leaving the row out"
    )


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #


def test_a_nan_in_the_reference_set_is_refused() -> None:
    """A distance to a NaN is a NaN, and `NaN > threshold` is **False** — so an unfilled
    feature would silently mean "not dissimilar" and the refusal would never fire. That
    is a gate that reports success while doing nothing, which invariant 3 forbids."""
    reference = cloud(50, spread=1.0, seed=3)
    reference[7, 2] = np.nan
    with pytest.raises(di.DissimilarityError, match="NaN or infinity"):
        fit_on(reference, 50)


def test_a_nan_in_the_scored_vector_is_refused() -> None:
    fitted = a_fit(300)
    vector = np.zeros(fitted.width)
    vector[1] = np.nan
    with pytest.raises(di.DissimilarityError, match="NaN or infinity"):
        di.score(fitted, vector)


def test_a_vector_of_the_wrong_width_is_refused() -> None:
    fitted = a_fit(300)
    with pytest.raises(di.DissimilarityError, match="against the reference set's"):
        di.score(fitted, np.zeros(fitted.width + 1))


def test_an_identity_that_does_not_match_the_rows_is_refused() -> None:
    """The identity is the proof of which rows were seen; a mismatch makes it a proof of
    nothing, and it would still load, still score and still look like an artefact."""
    reference = cloud(50, spread=1.0, seed=5)
    with pytest.raises(di.DissimilarityError, match="identity has"):
        di.fit(
            reference,
            identity(49),
            neighbours=NEIGHBOURS,
            percentile=PERCENTILE,
            decision_ts=stamps(50),
            exclusion_s=SPAN_S,
        )


def test_a_percentile_outside_zero_to_one_is_refused() -> None:
    reference = cloud(50, spread=1.0, seed=5)
    with pytest.raises(di.DissimilarityError, match="percentile must be in"):
        fit_on(reference, 50, percentile=1.0)


def test_too_few_reference_rows_for_k_is_a_stop_rather_than_a_smaller_k() -> None:
    """Quietly reducing `k` would make the DI mean something different on the folds
    where history is thinnest, which are the folds it matters most on."""
    reference = cloud(NEIGHBOURS, spread=1.0, seed=5)
    with pytest.raises(di.DissimilarityError, match="cannot support"):
        fit_on(reference, NEIGHBOURS)


# --------------------------------------------------------------------------- #
# The exclusion span - ruling of 2026-09-15, amending ruling 6
# --------------------------------------------------------------------------- #


def test_same_moment_rows_on_other_pairs_are_left_out_of_the_distribution() -> None:
    """The defect the ruling names, constructed.

    Six pairs on 300 bars, and on each bar every pair carries the same market state plus a
    little noise - which is what 78 macro columns identical across pairs, and the calendar
    columns, do to a real reference set. Leaving out the row alone, a row's five nearest
    neighbours are the other five pairs on its own bar, so the distribution collapses to
    the noise and the threshold measures time proximity: every live candidate, which has no
    same-moment neighbour, lands above it. Leaving out every row within the span, the
    neighbours come from other moments and the distribution is the market's spread.
    """
    pairs, bars = 6, 300
    rng = np.random.default_rng(21)
    market = rng.normal(size=(bars, 4))
    noise = rng.normal(scale=1e-3, size=(bars * pairs, 4))
    reference = np.repeat(market, pairs, axis=0) + noise
    ts = np.repeat(np.arange(bars, dtype=np.int64) * BAR_S, pairs)
    ids = [f"P{index % pairs}USD|{int(stamp)}" for index, stamp in enumerate(ts)]

    fitted = di.fit(
        reference,
        ids,
        neighbours=NEIGHBOURS,
        percentile=PERCENTILE,
        decision_ts=ts,
        exclusion_s=SPAN_S,
    )
    excluded = brute_force_distribution(reference, ts, neighbours=NEIGHBOURS, span_s=SPAN_S)
    row_only = brute_force_distribution(reference, ts, neighbours=NEIGHBOURS, span_s=None)

    assert np.allclose(fitted.distribution, excluded, rtol=1e-9, atol=1e-9), (
        "the fitted distribution is not the leave-one-out with every row within the span "
        "left out"
    )
    assert float(np.median(excluded)) > 100.0 * float(np.median(row_only)), (
        "the constructed case cannot tell the exclusion from leave-one-out on the row alone"
    )
    assert fitted.threshold == pytest.approx(float(np.quantile(excluded, PERCENTILE)))
    assert fitted.exclusion_s == SPAN_S
    assert np.array_equal(fitted.decision_ts, ts)


def test_the_span_is_inclusive_at_exactly_exclusion_s() -> None:
    """A row exactly `exclusion_s` away is left out; one second further is not.

    Five rows on one axis. Row 0's nearest point in space is row 1, exactly the span away
    in time, so an exclusive boundary would give it a distance of 0.001; inclusive, its
    nearest candidate is row 2, one second outside the span, at 0.5.
    """
    reference = np.array([[0.0], [0.001], [0.5], [1.0], [2.0]])
    ts = [0, SPAN_S, SPAN_S + 1, 5 * SPAN_S, 6 * SPAN_S]
    ids = [f"AAAUSD|{stamp}" for stamp in ts]

    inclusive = di.fit(
        reference, ids, neighbours=1, percentile=0.5, decision_ts=ts, exclusion_s=SPAN_S
    )
    assert inclusive.distribution[0] == pytest.approx(0.5), inclusive.distribution
    narrower = di.fit(
        reference, ids, neighbours=1, percentile=0.5, decision_ts=ts, exclusion_s=SPAN_S - 1
    )
    assert narrower.distribution[0] == pytest.approx(0.001), narrower.distribution


def test_decision_ts_that_does_not_match_the_rows_is_refused() -> None:
    reference = cloud(200, spread=1.0, seed=5)
    with pytest.raises(di.DissimilarityError, match="decision_ts has shape"):
        fit_on(reference, 200, decision_ts=stamps(199))


@pytest.mark.parametrize("span", [0, -SPAN_S])
def test_a_span_that_is_not_positive_is_refused(span: int) -> None:
    """Zero is leave-one-out on the row alone, which is the defect rather than a variant."""
    reference = cloud(200, spread=1.0, seed=5)
    with pytest.raises(di.DissimilarityError, match="exclusion_s must be positive"):
        fit_on(reference, 200, exclusion_s=span)


def test_a_row_left_with_fewer_than_k_candidates_is_a_stop() -> None:
    """60 rows one bar apart: rows 12 to 47 are within 48 bars of every other row, so they
    keep no candidate at all. A narrower span or a smaller k chosen here would change what
    the DI means on exactly the folds where history is thinnest."""
    reference = cloud(60, spread=1.0, seed=5)
    with pytest.raises(di.DissimilarityError, match="keep fewer than 5 neighbours"):
        fit_on(reference, 60)


# --------------------------------------------------------------------------- #
# The artefact
# --------------------------------------------------------------------------- #


def test_a_saved_fit_round_trips_with_its_identity(tmp_path: Path) -> None:
    fitted = a_fit(150)
    path = tmp_path / "di.npz"
    di.save(fitted, path)
    loaded = di.load(path)
    assert loaded.identity == fitted.identity
    assert loaded.threshold == fitted.threshold
    assert loaded.neighbours == fitted.neighbours
    assert loaded.percentile == fitted.percentile
    assert loaded.exclusion_s == fitted.exclusion_s == SPAN_S
    assert np.array_equal(loaded.decision_ts, fitted.decision_ts)
    assert np.array_equal(loaded.distribution, fitted.distribution)
    assert np.array_equal(loaded.reference, fitted.reference)
    assert di.score(loaded, fitted.reference[0]).di == di.score(fitted, fitted.reference[0]).di


def test_loading_needs_no_pickle(tmp_path: Path) -> None:
    """An object array in an `.npz` is unpickled on load, which is arbitrary code running
    inside the process that places orders — the same objection that keeps the scaler in
    JSON. Identity is stored as one joined string so `np.load` needs no `allow_pickle`.

    Asserted by loading with the default, which raises on a pickled array.
    """
    fitted = a_fit(300)
    path = tmp_path / "di.npz"
    di.save(fitted, path)
    with np.load(path) as payload:  # allow_pickle defaults to False
        assert set(payload.files) >= {"reference", "identity", "distribution", "threshold"}


def _rewrite(path: Path, *, drop: tuple[str, ...], **replace: object) -> None:
    with np.load(path) as payload:
        kept = {name: payload[name] for name in payload.files if name not in drop}
    kept.update(replace)
    np.savez_compressed(path, **kept)


def test_loading_a_di_fitted_without_the_exclusion_is_refused(tmp_path: Path) -> None:
    """A `di.npz` from before 2026-09-15 has no span. Its threshold measures time proximity
    and cannot be corrected without refitting, so it is refused rather than loaded with a
    default; engine 8 turns the refusal into `prediction_unavailable`."""
    path = tmp_path / "di.npz"
    di.save(a_fit(150), path)
    _rewrite(path, drop=("exclusion_s", "decision_ts"))
    with pytest.raises(di.DissimilarityError, match=r"records no exclusion_s.*time proximity"):
        di.load(path)


def test_loading_a_di_with_a_span_that_is_not_positive_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "di.npz"
    di.save(a_fit(150), path)
    _rewrite(path, drop=(), exclusion_s=np.int64(0))
    with pytest.raises(di.DissimilarityError, match="not positive"):
        di.load(path)
