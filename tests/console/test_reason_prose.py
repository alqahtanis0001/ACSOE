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
