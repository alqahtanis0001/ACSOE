"""The string side of the number rules in ``context/ui-context.md``.

Those rules are not stylistic. "Misread numbers cost money" is the first line of
that section, and every function here exists because of one of its six rules:

1. Tabular figures are CSS, not Python — that one lives in ``static/console.css``.
2. **Percentages are always explicitly signed.** :func:`format_signed_pct` writes
   ``+0.62%`` and never a bare ``0.62%``.
3. Colour is never the only signal, which is why the sign is written into the
   string rather than left to a class name.
4. Money renders to the precision it was stored at. :func:`format_money`
   therefore never re-rounds and never quantizes.
5. Anything older than ``console.stale_after_ms`` shows its age beside it —
   :func:`format_age`.
6. **A proper minus sign, U+2212, never a hyphen.** A hyphen is narrower than a
   digit in almost every face, so a column of hyphen-negative numbers does not
   align even with tabular figures switched on.

**No money value here ever touches ``float``.** ``Decimal`` arrives, a string
leaves, and a money value that passed through ``float`` anywhere on that path
would already have lost the precision these rules exist to protect. The single
``float`` in the module is :func:`format_rate_pct`, which renders the
leaderboard's *statistics* — a win rate is not money and was never a ``Decimal``.

Two things here are not number rules but belong with them, because they are the
same kind of decision: :func:`operator_reason`, which is why a code never reaches
the screen, and :func:`format_outcome`, which is why ``target`` reads ``Target``.
Both are copy rules from the same document, and both exist so that no screen
decides for itself what a stored code says to a human.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from acsoe.clients.store.contracts import from_micros

__all__ = [
    "ABSENT",
    "DIRECTION_FLAT",
    "DIRECTION_NEGATIVE",
    "DIRECTION_POSITIVE",
    "MINUS_SIGN",
    "NO_REASON_RECORDED",
    "OUTCOME_WORDS",
    "PERCENT_PLACES",
    "REASON_PROSE",
    "direction",
    "format_age",
    "format_clock_time",
    "format_engine_name",
    "format_metric",
    "format_money",
    "format_optional_pct",
    "format_outcome",
    "format_rate_pct",
    "format_signed_pct",
    "format_timestamp",
    "operator_reason",
    "signed",
]

#: U+2212 MINUS SIGN. Written as a named escape rather than as the character
#: itself, for two reasons: this file stays ASCII, and a reader cannot mistake it
#: for the hyphen it is one pixel away from looking like. That distinction is the
#: whole point of rule 6.
MINUS_SIGN: Final = "\N{MINUS SIGN}"

#: Two decimal places on a percentage. The system's edges are fractions of a
#: percent, so one place would round a real edge away and three would suggest a
#: precision the model does not have.
PERCENT_PLACES: Final = 2

_SECONDS = 1_000
_MINUTES = 60 * _SECONDS
_HOURS = 60 * _MINUTES
_DAYS = 24 * _HOURS

#: `reason_code` to the sentence an operator reads, per rule 3 of the copy
#: section of ``ui-context.md``: "Rejection reasons are written for the operator,
#: not the log". The table exists so that a row whose stored ``reason`` is a bare
#: code — which the engines are free to write, since nothing constrains that
#: column — still reaches the screen as a sentence.
#:
#: Every entry is a plain restatement of what the code already says. **Nothing
#: here adds a number, a threshold or a cause the row did not carry**, because a
#: sentence invented in the view layer is a sentence nothing verifies.
#:
#: **Every key is a code some producer emits, and both directions are asserted**
#: in `tests/console/test_reason_prose.py`: an engine's code with no sentence
#: here renders "No reason was recorded." silently, and a sentence here with no
#: producer is prose describing a refusal this system cannot make. Spec 120
#: retired five of the second kind, which had survived because the inverse walk
#: only warned. A producer is any engine's `contracts.py` code, any `hold_reason`
#: value, or a code `clients/store/seed.py` writes.
REASON_PROSE: Final[Mapping[str, str]] = {
    "net_edge_below_hurdle": "Net edge did not clear the hurdle after fees",
    # The two fail-closed paths, deliberately not variants of the lines around
    # them. "The edge was too thin" is a normal Tuesday and this system refusing
    # almost everything is the point; "the gate could not reach its inputs" is a
    # data problem the operator may need to act on, and invariant 3 is why it
    # reads as a refusal either way. Requested by B for engines 10 and 11,
    # 2026-09-09; B's wording, kept verbatim so the producer and the consumer
    # cannot drift.
    "cost_inputs_unavailable": "The cost gate could not price this candidate",
    "risk_inputs_unavailable": "The risk gate could not size this candidate",
    # Engine 17 `safety` and engine 7 `scout`, completing the set. Added 2026-09-10 on
    # B's explicit yes; wording proposed by me and confirmed by B, which is the same
    # direction the two lines above travelled.
    #
    # `safety`'s own contracts note that `operator_reason` prefers the row's own prose
    # and that engine 17 always writes a sentence, so this entry is never reached today.
    # That is a property of what engine 17 writes *now*, not a guarantee, and the
    # fallback exists precisely for the row that does not carry a sentence. A code
    # absent from this table renders "No reason was recorded." with no error anywhere,
    # which is the failure this seam exists to prevent.
    "safety_inputs_unavailable": "The safety breaker could not read its inputs",
    "scout_inputs_unavailable": "The scout could not read the pairs it needs",
    "spread_wider_than_move": "The spread is wider than the expected move",
    "below_ordermin": "Position would be below the pair's minimum order size",
    "below_costmin": "Position value would be below the pair's minimum order value",
    "insufficient_quote_balance": "Not enough quote currency held to open this position",
    "max_concurrent_positions": "Already holding the maximum number of positions",
    # Engine 11 `risk`, B's spec 89, prose landed 2026-09-16 under spec 99. Invariant 6 —
    # one open position per pair — became reachable in Phase 6 and needed a sentence the
    # day the codes appeared; the enumeration went red within a day of B landing them,
    # which is the return on that test.
    #
    # B's wording, kept verbatim, the same arrangement as engines 4, 7, 10 and 11: the
    # producer writes the sentence and the consumer does not paraphrase it, so the two
    # cannot drift. Deliberately not a variant of `max_concurrent_positions` above, which
    # is a fact about the portfolio and is cleared by waiting; these are facts about *this
    # pair*.
    #
    # Two sentences rather than one because the two states are cleared by different
    # actions — a position is exited, a resting entry is cancelled — and the operator
    # reading the rejection row needs to know which. B's contracts module says the same
    # thing from the producing end.
    "position_open_on_pair": "This pair already holds an open position",
    "entry_resting_on_pair": "This pair already has an entry order resting on the book",
    # `outside_universe` sat here until spec 120, and it never had a producer. It
    # predates engine 7: spec 44 step 7 told B the key *already existed*, and B then
    # built the engine with twelve specific exclusion codes and emitted no generic
    # one. Nothing is lost — the codes below say which exclusion, and a tally keyed on
    # a bucket would have said less.
    #
    # Engine 7 `scout`, spec 46. The six per-exclusion codes, requested by B on
    # 2026-09-10 with B's own wording, kept verbatim so the producer and the consumer
    # cannot drift — the same arrangement as engines 4, 10 and 11. `below_ordermin`,
    # `below_costmin` and `insufficient_quote_balance` are above and are engine 11's:
    # `scout` reuses them deliberately rather than minting parallel codes, because it is
    # the same arithmetic and should read the same on screen.
    #
    # Not one of these carries a number, a threshold or a cause. The engines write prose
    # carrying the actual figure and `operator_reason` prefers it; a sentence invented
    # in the view layer is a sentence nothing verifies.
    "pair_rules_missing": "The exchange did not report rules for this pair",
    "no_live_quote": "No live price for this pair",
    "crypto_quoted": "This pair is priced in a volatile asset",
    # Deliberately not folded into `crypto_quoted`, on the lead's spec 43 ruling. When
    # `trading.stable_quote_currencies` is absent, `scout` cannot *show* a quote to be
    # stable and excludes it — but a universe that shrank by policy and one that shrank
    # because nobody supplied a config key look identical from the outside, and only the
    # second is a fault somebody must fix. So this sentence points at the configuration
    # rather than at the market, which is the entire reason the code exists separately.
    "quote_not_provably_stable": (
        "The stable currencies are not configured, so this pair's quote cannot be trusted"
    ),
    "no_quote_balance": "The account holds none of this pair's quote currency",
    # Added 2026-09-10 when the enumeration test went red on B landing the code — which
    # is the seam working rather than a surprise. **My wording, not B's**, because the
    # alternative was leaving the suite red while I waited; B has been asked to replace
    # it if it is wrong, and every other entry from engines 4, 7, 10, 11 and 17 is the
    # producer's own.
    #
    # Deliberately not a variant of `no_quote_balance` above. That one is "you hold
    # none of it", a fact about the account; this one is "we cannot tell what it is
    # worth", a fact about a mechanism nobody has built — nothing in this system
    # publishes a rate between the reporting currency and an arbitrary quote currency.
    # An operator who read the same sentence for both would go looking at their
    # balances for a fault that is not there.
    "no_fx_rate": "No exchange rate to value this pair's quote currency",
    # Spec 44, added 2026-09-10 the same way and with the same caveat — my wording, B
    # asked to replace it. Caught by the enumeration within a test run of B landing it,
    # and by the *wider* half of it: like `scout_inputs_unavailable` this is a statement
    # about the tick rather than about a pair, so B deliberately keeps it out of
    # `EXCLUSION_REASONS` and a tuple-based test would not have seen it.
    #
    # **This is a PASS, not a refusal**, and the sentence has to carry that. Nothing
    # qualifying is this system's honest default state, and `ui-context.md` is explicit
    # that a console which looks empty most of the time is telling the truth rather than
    # failing. So: what the system did, in the past tense, with no apology and no
    # suggestion that anything is wrong.
    "empty_universe": "No pair was tradable on this bar",
    # Engine 7, spec 144 (B): the universe was not empty, but the expected-move ranking
    # skipped every pair in it, each one a pair the anomaly or DI gate would refuse. Worded
    # apart from `empty_universe` because the account could trade; the market could not.
    "no_rankable_pair": "Every tradable pair was one the market checks would refuse on this bar",
    "barriers_below_tick_size": "This pair's price steps are too coarse for a stop",
    # Engine 13 `anomaly`, spec 72. Its sentence says **market** because this gate has no
    # opinion about the trade and could not form one.
    #
    # `outlier_market_state` stood above this line until spec 120: the seed generator's
    # Phase 0 spelling for the same fact, kept because seeded rows carried it. B's spec 119
    # repointed those rows to `market_anomalous`, so the older spelling has no producer and
    # its sentence described a refusal nothing could make.
    "market_anomalous": "Trading conditions on this pair look broken",
    # Engine 15 `skeptic`, spec 73. `meta_label_veto` was the seed's spelling for the same
    # fact and went with spec 120 for the same reason as `outlier_market_state` above; the
    # seeded rows now carry the engine's own `skeptic_veto`.
    "skeptic_veto": "A second model expects this entry to fail",
    # Engine 20 `tournament`, spec 74. Offline: an operator meets these in a research run's
    # output rather than on the live screen, and they still go through the same table because
    # `operator_reason` is the one thing that turns a code into a sentence. Three separate
    # lines because the fix differs: supply a digest, re-run the training, open a database.
    "tournament_no_digest": "No training digest was given, so no models were ranked",
    "tournament_no_oos": "The training run's out-of-sample rows are missing, so no models were ranked",
    "tournament_no_store": "No database is open, so the rankings could not be saved",
    # The fourth, and the fix is different again: the run's two output files disagree about
    # a fold, so the thing to do is find which file is wrong, not re-run anything blindly.
    "tournament_digest_mismatch": (
        "The training run's summary and its out-of-sample rows disagree, so no models were ranked"
    ),
    # Engine 20's promotion gate, spec 139. The first two are verdicts written on the run's
    # leaderboard row; the last two are refusals that wrote nothing.
    "promotion_too_few_trades": "Fewer than ten trades, too few to judge, so not promoted",
    "promotion_lower_bound_not_above_zero": (
        "The edge did not stay above zero once overlapping trades and every configuration "
        "tried were allowed for, so not promoted"
    ),
    "promotion_no_ledger": "The count of configurations tried is missing, so nothing was judged",
    "promotion_bad_trade": (
        "A trade's return could not be worked out in one currency, so nothing was judged"
    ),
    "skeptic_unavailable": "No second-opinion model is loaded, so this entry was not judged",
    "anomaly_unavailable": "No market-health model is loaded, so conditions were not checked",
    "anomaly_inputs_incomplete": "Some market-health inputs were missing for this pair",
    # Engine 8 `prediction`, spec 71. **`di_refused`, and `dissimilarity_index` is gone.**
    # The code fixed by `engine-contracts.md` and emitted by the engine is `di_refused`;
    # `dissimilarity_index` was the seed generator's older spelling for the same fact and
    # mapping both gave two codes one sentence, which `test_no_two_codes_share_a_sentence`
    # correctly refuses — an operator cannot tell two identical lines apart. It was the
    # first of the invented spellings to be retired and for two phases it was the only
    # seeded code with no entry here; the rows rendered anyway, because `seed.py` writes
    # prose and `operator_reason` prefers a row's own text over this table. That is the
    # mechanism spec 119 found had hidden the whole invented vocabulary, and B's spec 119
    # repointed the seeded rows to `di_refused`.
    "di_refused": "Conditions are unlike anything in training",
    # Deliberately not a variant of each other. The first is a data problem somebody must
    # fix — there is no model to predict with at all, which is the state a fresh clone is
    # in. The second is a model that is fine and inputs that are not, which is usually a
    # pair whose longest lookback has not filled and needs no action.
    "prediction_unavailable": "No usable model is loaded, so nothing was predicted",
    # Ruled 2026-09-13 after B-2's rehearsal. Deliberately not a variant of the line above:
    # there IS a usable model, and what is wrong is that a setting the operator changed does
    # not reach it. The sentence therefore points at the setting, because an operator told
    # "no usable model" would go looking for a missing artefact that is sitting right there.
    "di_percentile_mismatch": (
        "The refusal threshold setting does not match the loaded model, so it was not used"
    ),
    "prediction_inputs_incomplete": "Some inputs the model needs were missing for this pair",
    # Two more retired by spec 120, and these two were the sharp ones. `insufficient_depth`
    # said the order book was "too thin to fill without slippage" as though engine 9 had
    # refused the trade; engine 9 has one return point and one status, publishes no
    # estimate, and engine 10 `cost` is what refuses on the absence — so the screen named
    # a gate that does not exist, past the gate that actually stopped the trade. Engine 9's
    # own `book_too_thin` is below and says what is not known instead. `no_candidate_cleared`
    # said "nothing cleared the gates on this bar", which is the "engine 16 combines their
    # outputs" reading the 2026-09-16 gate ruling retired: engine 16 checks coherence, has
    # five specific codes, and never decides. Neither had a producer.
    #
    # Engine 4 `data_guard`, requested by A on 2026-09-09. Codes fixed by A so the
    # producer and the consumer cannot drift; prose is mine, and A's wording is kept
    # almost verbatim because it was already right.
    #
    # `missing_candle` is about a hole *inside* the published series, which reads
    # like a contradiction of `architecture-context.md` — a missing candle in the
    # historical archive means no trades occurred and is not a data error, and spec
    # 30 forbids the loader from inventing one. Both hold at once: the loader
    # refuses to invent a bar, the gate refuses to act on a series with a hole in
    # it. One is about labelling, the other about trading, and fail-closed points
    # the opposite way in each. Engine 4's README carries the same note.
    "market_data_stale": "Market data is older than the guard allows",
    "negative_spread": "The order book is crossed",
    # Reworded 2026-09-13 on the lead's ruling under the `missing_bars` seam, A-2's
    # wording. "A decision bar has no candle" reads as a hole in *this pair*, and engine
    # 3 pools the gap across every pair it tracks — so the only true statement the
    # published number supports is that nothing traded anywhere for a whole bar. The
    # previous sentence would have sent an operator to look at one pair's feed.
    "missing_candle": "No pair traded for a whole decision bar",
    # Deliberately not folded into `market_data_stale`. "Older than the guard
    # allows" is a *false sentence* when nothing has arrived at all, and it sends
    # the operator after a lagging feed when the fault is an absent one — a slow
    # socket and a stream that never connected have different causes and different
    # fixes. A's finding, and the prose is what settled it.
    "no_market_data": "No market data has arrived",
    # Engine 12 `regime`, found by spec 99's walk over every engine's contracts module
    # on 2026-09-16 — not requested by anybody, because nobody had noticed. Both codes
    # have been on disk since Phase 5 and rendered as silence the whole time: engine 12
    # writes the bare code into `reason` and publishes no `reason_code`, so
    # `operator_reason` recognises the stored text as a code, refuses to print it, and
    # finds nothing to look up. Six enumeration tests written one per engine could not
    # see a seventh engine, which is the entire argument for the walk.
    #
    # Deliberately not variants of each other. "This pair produced no feature row on
    # this bar" is engine 5 having nothing for the candidate at all; "the two inputs the
    # rules read are unfilled" is a feature row that exists with holes in the lookbacks
    # that matter here, which is the ordinary state of a young series and needs nothing
    # done about it. Neither is a default label — engine 12 publishes `null` rather than
    # calling an unclassifiable market `choppy`, and the sentence has to say the market
    # was **not classified** rather than imply it was classified as quiet.
    "no_feature_row": "No feature row for this pair on this bar, so the market was not classified",
    "regime_inputs_incomplete": (
        "The inputs that classify the market have not filled yet for this pair"
    ),
    # Engine 21 `position_manager`, B's spec 92. B's contracts module flags both to spec
    # 99 by name. **My wording, not B's** — B is not running and the alternative was
    # leaving the walk red; the same arrangement as `no_fx_rate` and
    # `barriers_below_tick_size` above, and B is asked to replace either if it is wrong.
    #
    # A fill engine 21 could not turn into a position row, because the pair rules it
    # needs for `base` and `quote` were not published this tick. Nothing is lost: the
    # order stays resting in the store and the fill is picked up again next tick, and the
    # sentence says so, because "could not record your position" with no further word is
    # the most alarming thing this console could say about money.
    "position_unrecordable": (
        "An entry filled before the exchange published this pair's rules, so the position "
        "is recorded on the next tick"
    ),
    # Engine 16 `decision`, B's spec 90, landed 2026-09-16 and caught by the walk within
    # minutes of landing — the second time in one day, and the argument for the walk in
    # two lines. **My wording, not B's**, for the same reason as engine 21's above.
    #
    # Engine 16 is a gate and it *composes* the order intent; it never decides. The
    # sentences say "check" and "refused" and never "decided", because a README that
    # says composes and a console that says decided would put the ruling back at issue
    # in the one place nobody looks.
    #
    # Five codes, five different things to look at, so five sentences. The engine writes
    # the specific pair names and timestamps into its own `reason` and `operator_reason`
    # prefers that, which is why none of these carries a number.
    "pair_disagreement": "Two engines judged different pairs on this bar, so no entry was made",
    "stale_bar": "One of the approvals came from an earlier decision bar",
    "input_missing": "An engine this check needs published nothing for this bar",
    "no_approved_quantity": "The risk gate approved an entry without a size, so none was placed",
    "decision_inputs_unavailable": "The final coherence check could not read what it needs",
    "candidate_quote_not_live": "The chosen pair's price was stale or crossed at the last check, so no entry was made",
    # Engine 18 `execution`, B's spec 91, landed 2026-09-16 and caught by the walk the
    # same way engines 16 and 21 were — three engines in one afternoon. My wording, B
    # asked to replace any that is wrong.
    #
    # **The first of these is not a refusal**, and it is the reason engine 18 has codes
    # at all: the engine is not a gate, `entry_placed` says what it *did*, and a
    # placement with no sentence would be the one outcome the console cannot narrate.
    # So it is written in the past tense with no apology, the way `empty_universe` is.
    "entry_placed": "A post-only buy is resting on the book",
    # Not a variant of the line above and not an error either. Invariant 8: one entry
    # per tick, identified by `userref`, so meeting the order again is the mechanism
    # working on a re-run rather than anything going wrong.
    "entry_already_placed": "This entry was already placed, so nothing was sent again",
    # Invariant 7 in one sentence. The order is abandoned for the tick and deliberately
    # **not** re-placed lower, because re-placing at a worse price is chasing, and the
    # sentence says the price moved rather than that something failed.
    "post_only_would_cross": "The price moved before the order rested, so it was not placed",
    # **Rewritten 2026-09-16, and the old sentence was describing a repaired defect.**
    # It said the system "cannot describe" the order because `OrderState` carries no
    # quantity or limit price. A's spec 84 amendment added `qty`, `limit_price` and
    # `opened_at`, and B now builds the row, so the ordinary crash-recovery case has
    # moved to `entry_recovered_from_exchange` below. What is left here is the one thing
    # the amendment does not fix: the exchange answered with **no `opentm`**, so the
    # order cannot be dated, and a clock reading substituted for it would be a time that
    # never happened, written into the column research and this console read as a
    # placement time.
    #
    # So the sentence names the *specific* gap rather than a general inability, and it
    # still says what to do: the `userref` is published by engine 18 and is how an
    # operator finds the order. "when it was placed" rather than "`opentm`", because the
    # operator reads this screen and not Kraken's field list.
    "entry_unrecorded_at_exchange": (
        "An order is resting at the exchange and this system cannot tell when it was "
        "placed, so it was left unrecorded; find it by its reference"
    ),
    # The ordinary crash-recovery case, and **not** a refusal: the order came back fully
    # described, engine 18 wrote the row, and engine 21 will cancel it in the usual
    # unfilled window. Past tense, no apology. It has its own sentence rather than
    # sharing `entry_already_placed`'s because the two say different things to an
    # operator — that one is a tick re-run, this one is a process that died between
    # placing the order and recording it, and only the second is worth a second look.
    "entry_recovered_from_exchange": (
        "An order already at the exchange was matched to this entry and recorded"
    ),
    # The exchange contradicting the placement: invariant 8 makes every entry a
    # post-only buy limit, and the order under this entry's reference came back with no
    # limit price. No row is written, because a limit order with a null price is one
    # engine 21 cannot reason about.
    #
    # The sentence says **the exchange** reported it, not that the system failed, and
    # that is the whole of its job: this is not the breaker's business — a raise here
    # would become an `ERROR` block record and spend `safety.max_errors_in_window` on an
    # exchange disagreeing with itself about one order.
    "entry_at_exchange_is_not_a_limit": (
        "The exchange reports this entry with no limit price, so it was not recorded"
    ),
    # The first **hold** reason to get a sentence, and deliberately not written as a
    # refusal. Nothing was rejected and nothing is wrong with the position: the guard
    # refused this tick's market data, and a stop or target computed from exactly that
    # data would be a fabricated trigger, so engines 21 and 22 place no exit. The
    # position is still watched and an entry past its unfilled window is still cancelled.
    # An operator told "blocked" would go looking for a fault in the position; what is
    # paused is the exit, and what is not paused is the watching.
    "data_guard_blocked": (
        "Exits are paused while this tick's market data is rejected; the position is still "
        "watched"
    ),
    # Engine 22 `exit`, B's spec 93. Four codes here, and `data_guard_blocked` above is
    # the fifth — engine 22 spells its hold exactly as engine 21 does, on purpose, so
    # one fact keeps one sentence rather than growing a near-duplicate. That is the same
    # discipline that keeps "stop" and "stopped" out of one `trades` table.
    #
    # **Two of the four are not refusals and neither is an error.** Engine 22 is not a
    # gate; `reason_code` is how every engine says what it did, so the successful tick
    # and the quiet tick each need a sentence or the console narrates a placed exit as
    # silence.
    "exits_placed": "Exit orders are resting at the exchange for this position",
    "nothing_to_exit": "No position reached a barrier on this bar",
    # The re-run case, the same shape as `entry_already_placed` on the entry side and
    # for the same reason — invariant 8, one order per `userref`. Meeting the order
    # again is the mechanism working, not a fault.
    "exit_already_placed": "The exit for this position was already placed",
    # The one of the four that is a fault, and the sentence has to carry that the
    # position is **still open**: `positions_closed` is false beside this code and the
    # attempt repeats next tick. An operator told only "incomplete" would not know
    # whether the exposure is still theirs.
    "exit_incomplete": (
        "This position could not be exited and is still open; the attempt repeats next bar"
    ),
    # Engine 9 `order_book`, C's spec 96. **None of these is a refusal**, and that is
    # the engine's defining property rather than a detail: engine 9 never blocks on its
    # own criteria — it returns `OK` from exactly one return point — and publishes no
    # slippage estimate instead. Engine 10 `cost` is what refuses, on the absence.
    #
    # So every sentence says what is *not known*, never that something was rejected. An
    # operator reading "refused" here would go looking for a gate that does not exist.
    "book_fetch_failed": "The order book could not be read, so slippage is unknown",
    "book_unusable": (
        "The order book came back malformed, so slippage was not estimated from it"
    ),
    # Deliberately not "the book is thin" on its own. The fact that matters is that the
    # estimate would have to run past the depth fetched, and the levels nobody fetched
    # are the worst ones — so a guess here is optimistic by construction, which is
    # exactly the direction that gets a trade taken.
    "book_too_thin": (
        "The order book is too shallow to price this size within the depth fetched"
    ),
    # `no_quote_balance` is engine 7's code and already has its sentence above; engine 9
    # publishes the same spelling for the same fact and shares it, rather than adding a
    # second wording for one thing.
    #
    # Like `scout_inputs_unavailable`, this one is about the *setup* and not the book:
    # no candidate pair, no pair rules, no quote currency, a failed balance fetch, or
    # `order_book.depth` missing. The book itself may be perfectly fine.
    "order_book_inputs_unavailable": (
        "The order-book check could not read what it needs to price this size"
    ),
    # Engine 14 `adaptive_router`, C's spec 97. **All four mean the same consequence —
    # no weights — while meaning four different things to an operator**, which is why
    # they are four codes and get four sentences rather than one shared line. Two are
    # ordinary states and two are refusals to guess.
    #
    # A fresh clone. Not an error, and the sentence must not imply one.
    "leaderboard_empty": "No model has been through the tournament yet",
    # A refusal to weight on a partial view: the engine cannot see the whole table.
    "leaderboard_unreadable": (
        "The model leaderboard could not be read in full, so no weights were applied"
    ),
    # The subtler refusal, and the sentence says *longer than could be read* rather than
    # *missing*: a windowed read came back exactly full, so rows beyond it exist.
    # Weighting anyway would still sum to one, over the wrong set, and a version outside
    # the window would be absent because nobody looked rather than zero because it had
    # no edge — two states that are indistinguishable everywhere downstream.
    "leaderboard_truncated": (
        "The model leaderboard is longer than could be read, so no weights were applied"
    ),
    # A finding, not a fault, and the sentence says so plainly. Every version scored at
    # or below its own base rate: the leaderboard is reporting that nothing on it has
    # edge, which is information an operator wants stated rather than softened.
    "no_model_beats_its_base_rate": "No model is currently beating its own base rate",
    # Engine 19 `memory`, spec 104, landed in the same change as the code, as invariant 12
    # requires. **Engine 19's code, not the errored engine's**: it is the `block_reason` of
    # the row recording an opportunity-chain engine that raised, and it is never a
    # rejection, because an engine that raised decided nothing.
    #
    # So the sentence says the check *failed* rather than *refused*, and it says what to
    # do. A refusal is the system working and needs nothing; this is a fault somebody has
    # to read about, and the engine's own error is in the log for the tick, not on this
    # row. It also names the consequence the operator cares about first: nothing was
    # traded. It does not mention the error-rate breaker, which is a threshold this row
    # does not carry.
    "engine_errored": (
        "A check failed with an error before it could decide, so nothing was traded; "
        "the log for this tick says why"
    ),
}

#: What a row with neither prose nor a mapped code shows. A statement of absence,
#: in the voice of the empty state — never the bare code, and never a guess at
#: what the engine meant.
NO_REASON_RECORDED: Final = "No reason was recorded."

#: `TradeOutcome` to the operator word. The stored value is a code; the screen
#: says which barrier the position hit.
OUTCOME_WORDS: Final[Mapping[str, str]] = {
    "target": "Target",
    "stop": "Stop",
    "timeout": "Timeout",
    "liquidation": "Liquidation",
}

#: `snake_case_like_this` and nothing else. Used only to decide whether a stored
#: ``reason`` is a sentence or a code that leaked into the column; it is never
#: used to *derive* prose.
_CODE_LIKE: Final = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")

#: What a cell shows when the row does not carry the value. An em dash, which
#: reads as *absent*; a zero in a numeric column reads as a measured result, and
#: a `scout` rejection that never reached the cost gate has no net edge to report.
ABSENT: Final = "\N{EM DASH}"

#: The three directions a signed figure can have. These are the class names the
#: stylesheet keys its 2px rule off — the **sign** in the text carries the meaning
#: and the colour only reinforces it, so a red-green colourblind operator loses
#: nothing by never seeing them.
DIRECTION_POSITIVE: Final = "pos"
DIRECTION_NEGATIVE: Final = "neg"
DIRECTION_FLAT: Final = "flat"


def direction(value: Decimal | None) -> str:
    """Which way a signed figure points, as a class name.

    Zero is :data:`DIRECTION_FLAT` and not "positive". A flat outcome is neither
    a gain nor a loss, and colouring it green would overstate it — which is the
    same reason the palette's positive and negative are muted in the first place.
    """
    if value is None or not value.is_finite() or value == 0:
        return DIRECTION_FLAT
    return DIRECTION_NEGATIVE if value < 0 else DIRECTION_POSITIVE


def format_engine_name(name: str) -> str:
    """An engine's identifier as the operator reads it: ``data_guard`` -> "data guard".

    Not title-cased. The engines are named after what they do, and "Data Guard"
    reads like a product while "data guard" reads like a part of the system —
    which matches the sentence-case rule in ``ui-context.md``.
    """
    return name.strip().replace("_", " ")


def format_optional_pct(value: Decimal | None, *, places: int = PERCENT_PLACES) -> str:
    """A signed percentage, or :data:`ABSENT` when the row does not carry one."""
    return ABSENT if value is None else format_signed_pct(value, places=places)


def operator_reason(reason_code: str, reason: str = "") -> str:
    """The sentence the operator reads for one refused candidate or blocked tick.

    Three sources, in this order, and the order is a decision worth stating:

    1. **The row's own ``reason``, when it is already prose.** It is the most
       specific text available — "Net edge -0.21% after fees" carries the actual
       number, and no mapping keyed on a code ever can. Replacing it with the
       generic sentence for its code would throw away information the writer took
       the trouble to record.
    2. **:data:`REASON_PROSE` for the code**, when the stored text is empty or is
       itself a bare code. That is the case the mapping exists for.
    3. **:data:`NO_REASON_RECORDED`** when there is neither. Not the code — a code
       on screen is the defect this function exists to prevent — and not an
       invented sentence either.
    """
    text = reason.strip()
    if text and not _CODE_LIKE.match(text):
        return text
    mapped = REASON_PROSE.get(reason_code.strip())
    if mapped:
        return mapped
    return NO_REASON_RECORDED


def format_outcome(outcome: str) -> str:
    """The operator word for a stored outcome code.

    An unmapped value is title-cased rather than mapped to a guess: a new barrier
    the console has not been taught about should read as itself, not as one of the
    four it knows.
    """
    key = outcome.strip()
    return OUTCOME_WORDS.get(key.lower(), key.replace("_", " ").capitalize())


def format_clock_time(micros: int) -> str:
    """``HH:MM:SS`` in UTC, for the cycle feed's time column.

    UTC, never a local zone. The daemon writes microseconds since the epoch and
    the operator may not be sitting in the same zone as the machine; a feed whose
    times silently shift with the viewer's clock cannot be compared against a log.
    """
    return from_micros(micros).strftime("%H:%M:%S")


def format_timestamp(micros: int) -> str:
    """``YYYY-MM-DD HH:MM:SS`` in UTC, for history and the leaderboard.

    History spans days, so the date is part of the value there in a way it is not
    in a feed of the current run's ticks.
    """
    return from_micros(micros).strftime("%Y-%m-%d %H:%M:%S")


def format_rate_pct(value: float | None, *, places: int = PERCENT_PLACES) -> str:
    """A **proportion** rendered as a percentage, deliberately unsigned.

    Rule 2 of ``ui-context.md`` — always explicitly signed — is about *directional*
    values, where a missing sign is a missing direction. A win rate has no
    direction: it runs 0 to 1, and writing ``+62.00%`` would imply a change of
    +62 points against something. So the sign rule does not apply here, and this
    is the only percentage in the console that does not carry one.

    ``float`` is correct here and only here: the leaderboard's metrics are
    statistics, not money. ``None`` renders as an em dash, which reads as absent
    rather than as zero.
    """
    if value is None:
        return ABSENT
    return format(value * 100, "." + str(places) + "f") + "%"


def format_metric(value: float | None, *, places: int = PERCENT_PLACES) -> str:
    """A leaderboard statistic that is not a percentage — Sharpe, deflated Sharpe, Brier.

    ``float`` is correct here for the same reason as :func:`format_rate_pct`: these
    are statistics, never money. A negative one keeps its proper minus sign so the
    column still aligns, and ``None`` reads as absent rather than as zero — an
    unscored model and a model that scored 0.00 are not the same thing.
    """
    if value is None:
        return ABSENT
    return signed(format(value, "." + str(places) + "f"))


def signed(text: str) -> str:
    """Replace a leading ASCII hyphen with a proper minus sign.

    Applied to the *rendered* string rather than to the number, because
    ``Decimal.__str__`` is the thing that writes the hyphen and it is the only
    place one can enter.
    """
    return MINUS_SIGN + text[1:] if text.startswith("-") else text


def format_money(value: Decimal, *, currency: str | None = None) -> str:
    """A money value at exactly the precision it was stored at.

    No quantizing. ``Decimal("1000.00")`` means cents and ``Decimal("1000")``
    means units; the trailing zeros are the quantum the writer chose, and
    normalising them away throws information that came from the exchange's own
    ``pair_decimals``. ``format(value, "f")`` also refuses scientific notation,
    which ``str(Decimal("1E+3"))`` would otherwise produce.

    A non-finite value is not formatted. ``Decimal("NaN")`` would render as the
    text ``NaN`` and sit in a column of prices looking like a value.
    """
    if not value.is_finite():
        raise ValueError(f"refusing to render a non-finite money value: {value!r}")
    rendered = signed(format(value, "f"))
    return rendered if currency is None else f"{rendered} {currency}"


def format_signed_pct(value: Decimal, *, places: int = PERCENT_PLACES) -> str:
    """A ratio rendered as an explicitly signed percentage.

    The argument is a **ratio**, per ``code-standards.md``: ``Decimal("0.0062")``
    is 0.62% and renders ``+0.62%``. Passing ``0.62`` and getting ``+62.00%`` is
    correct behaviour, not a bug — the unit belongs to the caller and the variable
    name is where it is declared.

    Zero renders ``+0.00%``. That looks odd and is deliberate: rule 2 says always
    explicitly signed, and a bare ``0.00%`` in a column of signed figures reads as
    a missing value rather than as a flat one.
    """
    if not value.is_finite():
        raise ValueError(f"refusing to render a non-finite percentage: {value!r}")
    if places < 0:
        raise ValueError("places must not be negative")
    exponent = Decimal(1).scaleb(-places)
    percent = (value * 100).quantize(exponent, rounding=ROUND_HALF_UP)
    if percent.is_signed() and percent != 0:
        return MINUS_SIGN + format(-percent, "f") + "%"
    # `is_signed()` is true for Decimal("-0.00"), which must not print as a
    # negative zero: the sign would be reporting a direction the number does not
    # have.
    return "+" + format(abs(percent), "f") + "%"


def format_age(milliseconds: int) -> str:
    """How old a figure is, in the shortest honest form.

    Shown beside any figure past ``console.stale_after_ms``. Deliberately coarse:
    the operator needs to know whether the screen is seconds or minutes behind,
    and a millisecond-precision age on a one-minute loop is noise that changes on
    every poll.

    A negative age is rendered as ``0s`` rather than refused. It means the clock
    the console was given is behind a timestamp the daemon wrote, which is a
    two-process skew and not something the console can fix or should crash over.
    """
    remaining = max(milliseconds, 0)
    if remaining < _SECONDS:
        return f"{remaining}ms"
    if remaining < _MINUTES:
        return f"{remaining // _SECONDS}s"
    if remaining < _HOURS:
        return f"{remaining // _MINUTES}m {(remaining % _MINUTES) // _SECONDS:02d}s"
    if remaining < _DAYS:
        return f"{remaining // _HOURS}h {(remaining % _HOURS) // _MINUTES:02d}m"
    return f"{remaining // _DAYS}d {(remaining % _DAYS) // _HOURS:02d}h"
