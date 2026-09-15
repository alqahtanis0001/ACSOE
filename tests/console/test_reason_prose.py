"""Every reason code an engine emits reaches the operator as a sentence. Spec 46.

`ownership.md`'s seam table: *"A code absent from the map renders 'No reason was
recorded.' — silently, with no error anywhere."* That silence is the whole problem. The
console does not raise, does not log, and does not degrade visibly; the operator simply
gets a screen that declines to say why a pair was refused, and nothing anywhere records
that a code went unmapped.

**The codes are enumerated out of the producing module, never listed by hand.** A
hand-written list drifts the first time B adds a code, and it drifts in the direction
this seam is known for: silently, on the console, at the moment somebody is trying to
find out why the universe shrank. Enumerating means the test goes red when a code is
added and unmapped, which is the only moment anyone can act on it cheaply.

`REASON_PROSE` is C's and the code strings are the producing engine's. Both halves are
read here rather than restated, so neither can be wrong about the other.
"""

from __future__ import annotations

from types import ModuleType, SimpleNamespace

import pytest

from acsoe.console.format import NO_REASON_RECORDED, REASON_PROSE, operator_reason
from acsoe.engines.scout import contracts as scout_contracts


def declared_reason_codes(module: ModuleType | SimpleNamespace) -> dict[str, str]:
    """Every `REASON_*` string constant a contracts module declares, by attribute name.

    Broader than the module's own `EXCLUSION_REASONS` tuple on purpose. That tuple is
    the exhaustive list of ways a *pair* can be excluded and is ordered by the filter's
    own application order, so it deliberately leaves out codes that are statements about
    the tick rather than about a pair — `scout_inputs_unavailable` is one. A test
    enumerating only the tuple would let exactly those codes go unmapped, and they are
    the ones an operator meets when something is broken rather than when the market is
    merely quiet.

    Reading the attributes means a code B adds is covered whether or not B remembers to
    put it in the tuple.
    """
    return {
        name: value
        for name, value in vars(module).items()
        if name.startswith("REASON_") and isinstance(value, str)
    }


def unmapped(module: ModuleType | SimpleNamespace) -> dict[str, str]:
    """The declared codes `REASON_PROSE` does not carry. Empty is the passing state.

    Factored out so the enumeration itself can be tested against a module that is
    deliberately missing an entry — see `test_the_enumeration_catches_a_code_nobody_mapped`.
    A check nobody has seen fail is a comment, and that applies to the mechanism as much
    as to the criteria it is modelled on.
    """
    return {
        name: code
        for name, code in declared_reason_codes(module).items()
        if code not in REASON_PROSE
    }


# --------------------------------------------------------------------------- #
# Engine 7 `scout` — spec 46
# --------------------------------------------------------------------------- #


def test_every_exclusion_reason_scout_declares_has_prose() -> None:
    """Spec 46's acceptance check, on the tuple the engine publishes its tally under.

    Every member of `EXCLUSION_REASONS` is a key an operator will meet on the empty
    state, because the tally is keyed by these codes.
    """
    missing = [code for code in scout_contracts.EXCLUSION_REASONS if code not in REASON_PROSE]
    assert not missing, (
        "engine 7 declares exclusion reason(s) with no operator prose: "
        f"{missing}. Each renders as {NO_REASON_RECORDED!r} on the console, silently."
    )


def test_every_reason_code_scout_declares_has_prose() -> None:
    """The wider net, which catches the codes `EXCLUSION_REASONS` deliberately omits.

    `scout_inputs_unavailable` is not in that tuple, and correctly so: it says the gate
    could not read its inputs at all, which is a fact about the tick rather than about
    any pair, and counting it in the tally would break `scanned == entered + sum(tally)`.
    It still reaches the console, so it still needs a sentence.
    """
    assert unmapped(scout_contracts) == {}


def test_the_tick_level_code_is_mapped_but_not_counted_as_an_exclusion() -> None:
    """Both halves of B's deliberate arrangement, pinned so neither drifts.

    If it were added to `EXCLUSION_REASONS` the tally arithmetic would stop adding up;
    if it were dropped from `REASON_PROSE` the operator would get silence on the one
    occasion the gate had actually broken.
    """
    assert scout_contracts.REASON_INPUTS_UNAVAILABLE in REASON_PROSE
    assert scout_contracts.REASON_INPUTS_UNAVAILABLE not in scout_contracts.EXCLUSION_REASONS


def test_the_two_crypto_quoted_codes_do_not_share_a_sentence() -> None:
    """The lead's spec 43 ruling, which is the reason there are two codes at all.

    A universe that shrank because the operator disabled crypto-quoted pairs and one
    that shrank because nobody supplied `trading.stable_quote_currencies` look identical
    from the outside, and only the second is a fault somebody must fix. Two codes
    rendering the same sentence would put them back to being indistinguishable and
    would undo the ruling in the view layer, where nothing else would notice.
    """
    by_policy = REASON_PROSE[scout_contracts.REASON_CRYPTO_QUOTED]
    by_absent_config = REASON_PROSE[scout_contracts.REASON_QUOTE_NOT_PROVABLY_STABLE]
    assert by_policy != by_absent_config
    assert "configur" in by_absent_config.lower(), (
        "the sentence for a quote that cannot be *shown* stable must point at the "
        "configuration rather than at the market, or the operator goes looking for the "
        "wrong fault: " + repr(by_absent_config)
    )


def test_scout_reuses_engine_elevens_codes_rather_than_minting_parallel_ones() -> None:
    """Same arithmetic, same meaning, same sentence on screen.

    Two codes for one condition would give the operator two different sentences for the
    same refusal depending on which gate got there first.
    """
    from acsoe.engines.risk import contracts as risk_contracts

    for name in (
        "REASON_BELOW_ORDERMIN",
        "REASON_BELOW_COSTMIN",
        "REASON_INSUFFICIENT_QUOTE_BALANCE",
    ):
        assert getattr(scout_contracts, name) == getattr(risk_contracts, name), name


# --------------------------------------------------------------------------- #
# Engine 8 `prediction` — spec 71
# --------------------------------------------------------------------------- #


def test_every_reason_code_prediction_declares_has_prose() -> None:
    """The same net over engine 8's contracts module, for the same reason.

    Engine 8 is the first engine whose refusals are a *model* declining rather than a gate
    refusing, and one of its three codes says nothing is wrong at all. An operator meeting
    silence in the reason column would have no way to tell that apart from a fault.
    """
    from acsoe.engines.prediction import contracts as prediction_contracts

    assert unmapped(prediction_contracts) == {}


def test_the_two_load_failures_and_the_incomplete_inputs_do_not_share_a_sentence() -> None:
    """Three refusals, three meanings, and only one of them is somebody's to fix.

    `prediction_unavailable` is "there is no model at all", which is where a fresh clone
    lives and which needs a trained run and a config key. `prediction_inputs_incomplete` is
    a model that is fine and a pair whose longest lookback has not filled, which usually
    needs nothing. `di_refused` is the model declining to answer, which is the system
    working. One sentence across them would send an operator looking for a fault that is
    not there, or leave a real one unlooked-for.
    """
    from acsoe.engines.prediction import contracts as prediction_contracts

    sentences = {
        REASON_PROSE[prediction_contracts.REASON_UNAVAILABLE],
        REASON_PROSE[prediction_contracts.REASON_INPUTS_INCOMPLETE],
        REASON_PROSE[prediction_contracts.REASON_DI_REFUSED],
    }
    assert len(sentences) == 3


def test_the_seed_generators_older_di_spelling_still_renders_because_it_carries_prose() -> None:
    """`dissimilarity_index` was retired from the map with spec 71 and nothing regressed.

    `engine-contracts.md` fixes the code as `di_refused` and engine 8 emits that;
    `clients/store/seed.py` still writes `dissimilarity_index` on its seeded rows. Mapping
    both gave one sentence to two codes, which the test below refuses for good reason. The
    seeded rows are unharmed because they carry their own prose and `operator_reason`
    prefers it — asserted here rather than claimed, because "it renders fine" is exactly the
    kind of thing that is true until it is not.

    The spelling in `seed.py` is B's file and is raised with the lead.
    """
    assert "dissimilarity_index" not in REASON_PROSE
    assert (
        operator_reason(
            "dissimilarity_index", "Conditions unlike anything in training (DI 0.97)"
        )
        == "Conditions unlike anything in training (DI 0.97)"
    )
    assert operator_reason("dissimilarity_index", "") == NO_REASON_RECORDED


def test_the_percentile_mismatch_points_at_the_setting_not_at_a_missing_model() -> None:
    """Ruled 2026-09-13. There *is* a usable model; a setting the operator changed does not
    reach it, because the DI threshold is baked into the artefact.

    An operator told "no usable model is loaded" would go looking for a missing artefact that
    is sitting right there, so the two sentences have to differ in what they point at.
    """
    from acsoe.engines.prediction import contracts as prediction_contracts

    sentence = REASON_PROSE[prediction_contracts.REASON_DI_PERCENTILE_MISMATCH]
    assert sentence != REASON_PROSE[prediction_contracts.REASON_UNAVAILABLE]
    assert "setting" in sentence.lower()
    for missing_model in ("no usable model", "not loaded", "no model"):
        assert missing_model not in sentence.lower(), missing_model


def test_the_di_refusal_reads_as_the_model_declining_rather_than_as_a_fault() -> None:
    """`ui-context.md` rule 3: rejection reasons are written for the operator.

    This one refusal means the system is working exactly as designed, and the sentence has
    to carry that. Anything reading as an error would have an operator investigating the
    single case where there is nothing to investigate.
    """
    from acsoe.engines.prediction import contracts as prediction_contracts

    sentence = REASON_PROSE[prediction_contracts.REASON_DI_REFUSED].lower()
    for alarming in ("error", "failed", "could not", "unavailable", "broken"):
        assert alarming not in sentence, (alarming, sentence)


# --------------------------------------------------------------------------- #
# Engine 13 `anomaly` — spec 72
# --------------------------------------------------------------------------- #


def test_every_reason_code_anomaly_declares_has_prose() -> None:
    from acsoe.engines.anomaly import contracts as anomaly_contracts

    assert unmapped(anomaly_contracts) == {}


def test_the_anomaly_block_says_market_rather_than_trade() -> None:
    """Invariant 4, in the view layer.

    Engine 13 judges the market and has no opinion about the candidate — it cannot even see
    one. A sentence implying the *trade* was rejected would tell an operator the system
    formed a view it did not form, and it is the kind of thing that gets repeated back as
    fact in a dissertation.
    """
    from acsoe.engines.anomaly import contracts as anomaly_contracts

    sentence = REASON_PROSE[anomaly_contracts.REASON_MARKET_ANOMALOUS].lower()
    assert "condition" in sentence or "market" in sentence, sentence
    for about_the_trade in ("trade", "entry", "edge", "signal"):
        assert about_the_trade not in sentence, (about_the_trade, sentence)


# --------------------------------------------------------------------------- #
# Engine 15 `skeptic` — spec 73
# --------------------------------------------------------------------------- #


def test_every_reason_code_skeptic_declares_has_prose() -> None:
    from acsoe.engines.skeptic import contracts as skeptic_contracts

    assert unmapped(skeptic_contracts) == {}


def test_the_skeptic_veto_reads_as_a_refusal_and_never_as_an_approval() -> None:
    """Invariant 4, in the view layer.

    There is no output of engine 15 that makes a trade more likely, and the sentence has to
    carry that. A line an operator could read as the system endorsing an entry would be the
    one place a veto-only model appeared to have approved something.
    """
    from acsoe.engines.skeptic import contracts as skeptic_contracts

    sentence = REASON_PROSE[skeptic_contracts.REASON_VETO].lower()
    for approving in ("approve", "confidence", "endorse", "good", "strong"):
        assert approving not in sentence, (approving, sentence)


def test_the_two_skeptic_codes_and_the_seeded_one_are_three_sentences() -> None:
    """`meta_label_veto` is the seed generator's spelling and `skeptic_veto` is the engine's.

    They are kept apart rather than sharing a line, the way `di_refused` and the retired
    `dissimilarity_index` could not be: a shared sentence makes two codes one code as far as
    the operator is concerned, which `test_no_two_codes_share_a_sentence` refuses.
    """
    from acsoe.engines.skeptic import contracts as skeptic_contracts

    assert "meta_label_veto" in REASON_PROSE
    assert REASON_PROSE["meta_label_veto"] != REASON_PROSE[skeptic_contracts.REASON_VETO]


# --------------------------------------------------------------------------- #
# Engine 20 `tournament` — spec 74
# --------------------------------------------------------------------------- #


def test_every_reason_code_tournament_declares_has_prose() -> None:
    """Engine 20 is offline, and its codes still need sentences.

    An operator meets them in a research run's output rather than on the live screen, and
    `operator_reason` is the one thing that turns a code into a sentence wherever it is read.
    Leaving them out would give the same silence in a place nobody is watching for it.
    """
    from acsoe.engines.tournament import contracts as tournament_contracts

    assert unmapped(tournament_contracts) == {}


def test_the_four_tournament_refusals_name_four_different_fixes() -> None:
    """Supply a digest, re-run the training, open a database, find which of the run's two
    files is wrong. One sentence across them would send a reader to do the wrong one."""
    from acsoe.engines.tournament import contracts as tournament_contracts

    sentences = {
        REASON_PROSE[tournament_contracts.REASON_NO_DIGEST],
        REASON_PROSE[tournament_contracts.REASON_NO_OOS],
        REASON_PROSE[tournament_contracts.REASON_NO_STORE],
        REASON_PROSE[tournament_contracts.REASON_DIGEST_MISMATCH],
    }
    assert len(sentences) == 4


# --------------------------------------------------------------------------- #
# The enumeration itself, broken on purpose
# --------------------------------------------------------------------------- #


def test_the_enumeration_catches_a_code_nobody_mapped() -> None:
    """The test above, shown to fail. `code-standards.md`: break the check you wrote.

    A hand-written list of codes passes this file's other tests just as well as an
    enumeration does — right up to the moment a code is added, which is the only moment
    either of them matters. So the mechanism is pointed at a module carrying a code that
    is deliberately absent from `REASON_PROSE`, and it has to notice.
    """
    fabricated = SimpleNamespace(
        REASON_PAIR_RULES_MISSING=scout_contracts.REASON_PAIR_RULES_MISSING,
        REASON_A_RULE_NOBODY_TOLD_THE_CONSOLE_ABOUT="quote_delisted_mid_tick",
    )
    assert unmapped(fabricated) == {
        "REASON_A_RULE_NOBODY_TOLD_THE_CONSOLE_ABOUT": "quote_delisted_mid_tick"
    }


def test_an_unmapped_code_really_does_render_as_silence() -> None:
    """Why the enumeration is worth having: the failure it prevents is invisible.

    No exception, no log line, no degraded rendering — just a sentence that declines to
    say anything, in the column whose entire job is to say why.
    """
    assert operator_reason("quote_delisted_mid_tick") == NO_REASON_RECORDED


# --------------------------------------------------------------------------- #
# The whole table
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("code", sorted(REASON_PROSE))
def test_no_prose_string_contains_a_digit(code: str) -> None:
    """Spec 46: no prose string carries a number, a threshold or a cause.

    A figure in this table is a figure nothing verifies. The engines write prose
    carrying the actual number — "Net edge -0.21% after fees" — and `operator_reason`
    prefers that over the mapping precisely because it is the more specific text. A
    threshold hardcoded here would be a second copy of a config value, on screen, with
    nothing to keep it true when the operator changes the real one.
    """
    sentence = REASON_PROSE[code]
    assert not any(character.isdigit() for character in sentence), (
        f"{code!r} carries a digit: {sentence!r}. The number belongs in the row's own "
        "reason, which `operator_reason` prefers anyway."
    )


def test_no_two_codes_share_a_sentence() -> None:
    """Two codes rendering identically are one code as far as the operator is concerned.

    The lead's spec 43 ruling is the specific case — `crypto_quoted` and
    `quote_not_provably_stable` exist separately precisely so a universe that shrank by
    policy is distinguishable from one that shrank for want of a config key — but the
    property is general, and it is the one that would quietly undo such a ruling in the
    view layer where nothing else looks.

    `no_fx_rate` and `no_quote_balance` are the newest pair at risk of it: "you hold
    none of this currency" and "we cannot tell what this currency is worth" are
    different faults in different places, and an operator given the same sentence for
    both would go looking at their balances for something that is not there.
    """
    by_sentence: dict[str, list[str]] = {}
    for code, sentence in REASON_PROSE.items():
        by_sentence.setdefault(sentence, []).append(code)
    shared = {sentence: codes for sentence, codes in by_sentence.items() if len(codes) > 1}
    assert not shared, (
        "these codes are indistinguishable on screen, so the operator cannot tell which "
        f"gate refused the candidate: {shared}"
    )


@pytest.mark.parametrize("code", sorted(REASON_PROSE))
def test_every_sentence_is_written_for_the_operator(code: str) -> None:
    """`ui-context.md`: *"Rejection reasons are written for the operator, not the log."*

    A sentence that is itself a bare code has the same effect as no sentence at all, and
    would pass a test that only checked the key was present.
    """
    sentence = REASON_PROSE[code]
    assert sentence.strip(), code
    assert sentence != code, f"{code!r} maps to itself, which renders a code on screen"
    assert " " in sentence, f"{code!r} maps to a single token, not a sentence: {sentence!r}"
    assert sentence[0].isupper(), f"{code!r} does not start with a capital: {sentence!r}"
