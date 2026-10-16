# Evidence pack 05 — the writer brief

**Read at commit `9f5a1449378c10e8f8f87ec27732914a0a19e92f` (`9f5a144`), `main`, clean tree, 2026-09-20T15:33Z–16:10Z.** This file is judgement, not evidence: every claim in it is backed by a pointer into packs 01–03, and those packs carry the file paths and line ranges. It is written in the report's own vocabulary — no build-phase numbers, no engine numbers, no agent names — because the report is for a reader who has never traded and has never read a line of the code.

## Contents

1. [Ten things a marker must not misread](#1-ten-things-a-marker-must-not-misread)
2. [Claims the report must not make](#2-claims-the-report-must-not-make)
3. [The real contribution, and the weakest point](#3-the-real-contribution-and-the-weakest-point)
4. [Figures and tables, chapter by chapter](#4-figures-and-tables-chapter-by-chapter)
5. [Things in the repository the writer would miss](#5-things-in-the-repository-the-writer-would-miss)
6. [Where the literature review is now out of date](#6-where-the-literature-review-is-now-out-of-date)
7. [How the eight chapters should divide the material](#7-how-the-eight-chapters-should-divide-the-material)
8. [Decisions for the operator before the writer starts](#8-decisions-for-the-operator-before-the-writer-starts)
9. [Writing for a reader who is neither a trader nor a programmer](#9-writing-for-a-reader-who-is-neither-a-trader-nor-a-programmer)
10. [A vocabulary map from the repository's words to the report's](#10-a-vocabulary-map-from-the-repositorys-words-to-the-reports)

---

## 1. Ten things a marker must not misread

Each has the sentence I would put in the report, then the evidence.

**1. The cheaper-fee run stopped itself, and that is the system working, not the system failing.**
Sentence: "Under the lower fee schedule the system took five trades in 27 hours, all on one pair and all losses; its own circuit breaker then froze trading for the remaining 76 of 91 days, exactly as its rules require after five consecutive losses. The frozen run is a result about the safety rules, not about the strategy's return."
Evidence: pack 03 §B.11 (the five rows, the freeze command at 2024-10-20 05:30Z, the block records); pack 02 §A.7 (the limit is 5, the action is freeze not liquidate).

**2. At the account's actual fee level the system cannot trade at all, by arithmetic, and this was proved before any simulation ran.**
Sentence: "At the fee level a new retail account is charged, the cost bar the system sets itself is 3.0% and its own forecast can never exceed 3.0%, so no trade is possible. This is a property of the design, established algebraically and confirmed over sixteen million forecasts; the simulations therefore ran at two fee levels the account does not have, declared as scenarios."
Evidence: pack 01 §B.5 (ii)/(i) the FINAL tier-1 proof; pack 02 §A.5 the measured tier.

**3. The spread assumption decides the sign of the result.**
Sentence: "With one constant bid–ask spread applied to every pair, the offline study showed a positive return per trade; with a spread that depends on each pair's liquidity, the same trades showed a return indistinguishable from zero and slightly negative. The simpler assumption inverted the sign because it priced thinly traded pairs as if they were liquid."
Evidence: pack 01 §B.5 (ii); pack 03 §B.7. The report must present this as a finding about method, and it must say that the simulation used the liquidity-dependent table and that no spread-sensitivity run was made (pack 03 §E items 11, 13).

**4. The decision to rank candidates by the model's own forecast was taken with the outcome grid in view, and the project says so.**
Sentence: "Ranking candidates by the forecast was adopted after a grid of trade counts had been computed on the same out-of-sample data. The stated reason was sample size — the count rose from 3 to 46 with the average return unchanged at about zero — and the acceptance bar was fixed before any run. The residual circularity is acknowledged rather than argued away."
Evidence: pack 01 §B.5 (iii) and the §R.2/§R.9 text quoted in pack 01 §B.4 context; pack 03 §B.9.

**5. "Not promoted" was the pre-registered expectation, not a surprise.**
Sentence: "Before the simulation started, the project computed that with roughly ten trades the acceptance bar would require an average net return of about 5% per trade, more than double what a single winning trade can return after costs; a non-promotion was therefore the expected outcome of the design, and the value of the run lies in its record."
Evidence: pack 03 §B.10 and §C.3.

**6. The evaluation is one season of one year, chosen for a deadline.**
Sentence: "The simulated window is three months (5 October 2024 to 4 January 2025), cut from six for the report deadline; it sits inside a strongly rising market in which Bitcoin gained about 58%, and it contains thirteen weekly retrainings. Nothing about it should be read as the system's behaviour over the eight years the models were trained across."
Evidence: pack 03 §E item 14, §C.4 (BTC +58.1% from the archive); pack 01 §B.5 (vi) §6a (the window's returns are essentially 2024's).

**7. Every non-price input to the simulation is a 2026 measurement applied to a 2024 window.**
Sentence: "The spread and depth come from 7.4 days of September 2026; the trading rules and the fee schedule are as published on 19 September 2026, after the exchange restructured its tiers in July 2026. Only the trades themselves are the period's own record. Every run stores this declaration on its own record."
Evidence: pack 02 §C.4, §A.3, §A.4; pack 01 §A.4 (the `runs` row's declaration).

**8. The second-opinion model's measured skill and the one the simulation used are different models.**
Sentence: "The veto model that showed clear skill in the eight-year study was trained on every earlier week's calls; the one the simulation ran was capped to the last thirteen weeks, and in the simulated window that capped model added no detectable selection beyond the forecast's own confidence. The eight-year numbers describe a model that no longer exists."
Evidence: pack 03 §B.4 and the tracker caveat it cites; pack 02 §B.3.

**9. The live-market program has never placed a real order and cannot yet.**
Sentence: "Live trading is refused by the configuration loader itself; the three-switch guard the design specifies is the next stage's deliverable. Every result in this report is from simulation or paper trading, and the simulation's market-data guard could not fire because replayed data has no outages."
Evidence: pack 01 §B.8; pack 03 §E items 22, 26.

**10. The gate that refused nearly everything was the cost check, and only the cost check.**
Sentence: "In both runs every refused candidate was refused by the cost check — 6,045 of 6,059 examined candidates in the dearer run — with a median forecast of 0.48% against a median bar of 1.00%. The other checks never had a candidate to refuse, so the runs say nothing about how often they would."
Evidence: pack 01 §A.4; pack 03 §E item 24; findings Part II §4.3–4.4.

## 2. Claims the report must not make

| Do not write | Because |
|---|---|
| "The dearer fee tier is safer / better than the cheaper one" | The difference is 4,920 versus 4,646 on nine and five trades; the cheaper run stopped on day 15. The only clean statement is which candidates the lower cost bar admitted and what those did (pack 03 §C.5). |
| "The system is profitable" or "the model has edge" | Both runs are below their start; the offline grids net about zero in every cell with every interval including zero; the acceptance bar is expected to reject (pack 03 §B.9, §B.10). |
| "The system was tested live" or "trades real money" | Live mode is refused by the loader; the order surface refuses (pack 01 §B.8). |
| "The system retrains itself / adapts as it trades" | The running program never trains; weekly retraining exists in the evaluation only (pack 02 §B.2). |
| "The adaptive weighting of models by recent performance was exercised" | The router has never weighted anything real; one model per week, no persisted leaderboard rows (pack 02 §B.7). |
| "The market-anomaly check / the veto model / the sizing check refused N candidates" | None refused anything in either run (pack 03 §E item 24). |
| "The results are statistically significant" or any p-value framed as a test of the strategy | The pre-registered statistic is a Bonferroni-widened interval over 1,679 trials; anything else is post hoc. No Benjamini–Hochberg procedure exists in the code (pack 03 §C.2). |
| "The bid–ask spread and slippage were measured for the simulated period" | They were declared from a 2026 recording (pack 02 §C.4). |
| "The recording is continuous since 8 September" | Four recorded gaps, two unrecoverable (pack 02 §C.2). |
| "This is the first veto-only meta-labelling / counterfactual rejection dataset in the literature" | No literature search exists in the repository (pack 03 §F claim 37). If the writer wants the claim, the literature review must earn it with its own search. |
| "The 405-fold walk-forward is the full study" | It stopped at fold 405 of 457 out of memory; no 2025 test week (pack 03 §B.1). |
| "The account's fee tier is 3 / 5" | It is tier 1, measured; 3 and 5 are scenarios (pack 02 §A.5). |
| "Every candidate on every bar was considered" | Half of all test rows never reach a forecast because a lookback window is unfilled (pack 03 §E item 18); one candidate per bar is examined. |
| "The DI feeds the regime classifier" | It does not; the field is a null placeholder (pack 03 §E item 25). |

## 3. The real contribution, and the weakest point

**The contribution.** The project's contribution is not a trading result; it is a piece of evaluation machinery built so that a negative answer is the natural output and a positive one would have to survive everything the machinery throws at it. Concretely: a decision pipeline in which every refusal is stored with the refusing check, the figures it compared and a per-feature explanation, and in which — since the last design change — every approval stores the verdict of every check that examined it, so both sides of every decision are answerable from the database; a cost model that is rebuilt from the live exchange every minute and that, at the account's real fee level, proves algebraically that no trade is possible; an acceptance bar fixed before the run, widened for overlapping holds and for the 1,679 configurations ever tried on the data; and a record of its own limitations written before any result existed. The finding that a single constant spread turns a null result into a positive one, and the finding that the cheaper fee schedule admitted a run of losers the dearer one refused, are both products of that machinery, and both would have been invisible to a conventional backtest. That the project can say, with rows to show, "the cost check refused 6,045 of 6,059 candidates by a median margin of 1.2 percentage points" is the contribution.

**The weakest point.** The evaluation rests on inputs the historical record does not contain, substituted from a different period, and on a window too short and too few trades to measure anything: the spread and depth are 7.4 days of September 2026 applied to late 2024, the exchange's rules and fees are 2026's, the window is one rising quarter, one run ended after five trades and the other will end near ten, below or at the threshold where the acceptance statistic even exists. The ranking rule the simulation used was chosen with a grid of results on the same data in view. The veto model's measured skill belongs to a version that was not run. And the whole build was gated on a machine with an unexplained intermittent memory fault, so every green gate is a retried measurement. The honest reading is that the project built an instrument and demonstrated that it works — it refused, it froze, it recorded — and that the instrument has not yet been pointed at a question it could answer with statistical force.

## 4. Figures and tables, chapter by chapter

CSV names refer to `04_figure_data.zip`.

**Introduction**
- Table: the account's measured fee level against the two simulated ones (`fee_schedule.csv`, rows 1–5). Caption: "The exchange's published fee schedule on 19 September 2026. The project's account is at tier 1; the simulations ran at tiers 3 and 5 as declared scenarios."

**Requirement analysis and specifications**
- Table: the safety limits and what each triggers (pack 02 §A.7). Caption: "Four limits, two actions: freeze or liquidate. Only a sustained data outage liquidates."
- Figure: the cost rule as one line of arithmetic with the tier-1 bar drawn above the 3% target. Caption: "At the entry fee level the bar (3.0%) meets the ceiling of any forecast (3.0%), so no trade is possible by construction."

**Methodology and system design**
- Figure: the three runtime chains as a flow, every check labelled with what it refuses on (`engines.csv`). Caption: "One tick of the loop: the guard runs every minute in every mode, the opportunity chain only on a closed 15-minute bar and only until the first refusal, the manage chain always."
- Figure: the triple-barrier label on one price path. Caption: "A label is which of three lines price touches first; a bar that touches two in one candle is labelled a loss."
- Table: the walk-forward window per fold, illustrated with fold 392 (`walkforward_folds.csv`). Caption: "Each week's model trains on the ninety days before its test week and nothing after; rows whose label windows reach the test week are purged and a 48-bar buffer is embargoed."
- Table: the declared substitutes with their dates (pack 02 §C.4). Caption: "What the 2024 archive lacks, and the 2026 measurement that stood in for each."
- Table: the liquidity buckets (`spread_buckets.csv`). Caption: "Bid–ask spread and depth by daily turnover, medians with interquartile ranges, from 7.4 days of recording in September 2026."

**Implementation**
- Table: one complete approval and one complete refusal as the database stores them (pack 01 §C.9). Caption: "Every check's figures on both sides of a decision. The refusal names its refuser; the approval names every check."
- Figure: the console's six panes (a screenshot the operator can take; the pane names are in pack 01 §C.5). Caption: "The read-only console: it renders the database and can send three commands."
- Table: reason codes and their plain-language sentences (pack 01 §C.8, an appendix).

**Testing and evaluation**
- Table: tests by kind with counts (pack 03 §A.1–A.2). Caption: "3,928 collected tests across eleven folders; every check has a test that it refuses and a test that it passes."
- Table: mutation sweeps per module, applied / killed / equivalent (pack 03 §A.3). Caption: "Planted defects and whether the tests caught them; every survivor was either killed by a new test or shown to be equivalent."
- Figure: per-fold Brier against base-rate Brier across the 405 folds (`walkforward_folds.csv`). Caption: "The forecast beats a constant prediction of each week's own target rate in most weeks by a small margin; accuracy is never reported because a model that always predicts the stop would score 51%."
- Figure: the offline funnel (`funnel_1p5y.csv`). Caption: "Of 53,022 decision bars in eighteen months, 74 clear the cost bar and one survives every check."
- Figure: the two equity curves with the BTC buy-and-hold series (`equity_tier3.csv`, `equity_tier5.csv`, `btc_window.csv`). Caption: "Both runs from 5,000; the cheaper-fee run froze on 20 October; Bitcoin rose 58% over the same window."
- Table: every trade of both runs (`trades_tier3.csv`, `trades_tier5.csv`). Caption: "Fourteen trades in total; every exit was a stop or a target, none a timeout."
- Table: refusals by reason (`rejections_by_reason_tier3.csv`, `_tier5.csv`). Caption: "Every refusal in both runs came from the cost check."
- Figure: candidates per tick — the chosen pair's forecast against the bar over time (`candidates_per_tick_tier3.csv`). Caption: "The ranking's usual choice is a stablecoin or currency pair on the forecast's low plateau; the trades come from the few bars where a volatile pair topped the ranking."
- Table: the pre-registered acceptance statistic with the placeholder tokens filled (pack 03 §C.2). Caption: "The bar, the trial count and the verdict per run."
- Figure: the spread inversion, flat versus bucket, cell by cell (`ranking_study.csv` and pack 03 §B.7). Caption: "The same trades under two spread assumptions."

**Discussion**
- Table: the power calculation (pack 03 §B.10). Caption: "What the bar would need at each trade count, against what a single winning trade returns."
- Figure: per-tick cost against tape volume by week (`tick_cost.csv`). Caption: "Simulation cost tracked the volume of the replayed tape."

**Conclusion / appendices**
- The abbreviations table (pack 01 §B.7); the invariants (pack 01 §B.2); the schema (pack 01 §C.7); the retired-vocabulary table (pack 01 §B.6); the known limitations table (pack 03 §E).

## 5. Things in the repository the writer would miss

- **The "first paper trade" walk-through** (`docs/build-log/phase-6/first-paper-trade.md`): every number of one simulated trade read from the rows, and the discovery that the database held no record of *why* the trade was taken. It is the origin of the approval record and the best single narrative of how the system decides.
- **The defects that only end-to-end runs found** (tracker "DEFECTS FOUND BY REHEARSAL", pack 01 context): a paper fill counted twice in equity that would have frozen the account on every trade; a tick on which a check crashed that was recorded nowhere; the exit-tick equity row that described no real instant. Each was found between two components that were individually correct and tested. This is the strongest material for a testing chapter about *what unit tests cannot see*.
- **The defect mutation testing structurally cannot reach** (tracker §"FINDING: a defect mutation testing structurally cannot reach"): a false positive on exactly one input no test author would write, found by a colleague reading the diff. Worth a paragraph on the limits of the method.
- **The Dissimilarity Index that measured time instead of distance** (tracker Finding 2): at the first threshold it refused 94.7% of live-shaped rows because the nearest neighbours of any training row were the same instant on other pairs. The fix (exclude every pair within 48 bars) and the measurement that found it are a clean example of a validation that looked like a cautious safety check and was a clock.
- **The retired-vocabulary check** (`docs_vocabulary`, pack 01 §B.6): a documentation consistency test that greps the specification for superseded terms, with a recorded account of what it cannot catch. Unusual, and a genuine engineering contribution to how a specification is kept true across 277 commits.
- **The trial ledger** (`docs/dataset/phase-7-trial-ledger.md`): 1,679 configurations enumerated one per line by a script, with the rule and every judgement, so the multiple-testing haircut is auditable. Few dissertations do this.
- **The native memory fault account** (tracker Known Risks, the long entry): the project's own statement that every gate was a retried measurement on faulty hardware, with the sites, the rates and what the mitigation covers. It belongs in Limitations verbatim in spirit.
- **The fee-schedule provenance** (pack 02 §A.4): the raw page committed beside the extracted table with hashes, and the exchange's restructure article. A model for how to cite a moving external source.
- **The exit-cycle equity row ruling** (tracker "FINDING, 2026-09-17"): why a single number ("equity") can describe no real instant when three components read the account at three moments, and the `cash_source` column that resulted.
- **The operator's rulings on freezing versus liquidating** (invariant 14, pack 01 §B.2): the reasoning that a drawdown is a statement about the past and an outage a statement about present knowledge, so only the latter liquidates. It is the design principle behind what happened to the cheaper-fee run.
- **The $49–$60 arithmetic** (findings §R.1) for what it costs a small account to reach tier 3 by trading volume, which is the practical framing of "cost-adaptive".

## 6. Where the literature review is now out of date

The writer already has: deterministic elimination before any model runs; retraining at the live cadence; adaptive routing by recent performance. Add:

- **"The candidate is chosen without any model"** — no longer true. Since the ranking change the candidate is ordered by the forecast's expected move (with pairs the anomaly and dissimilarity checks would refuse skipped), and the invariant that "a model may only ever make the system less willing to trade" was reworded to permit ordering (pack 01 §B.2, invariant 4 as amended). The universe *filter* is still model-free.
- **"Nine of the twenty-three components contain no machine learning"** — still the project's count, but the sentence must now carry the qualification that the universe component's *ordering* reads the forecast (pack 01 §B.1, the first paragraph of the overview).
- **"The Dissimilarity Index feeds regime detection"** — not implemented; the field is a null placeholder (pack 03 §E item 25).
- **"Anomaly detection over velocity, volume and spread"** — the detector is fitted without spread, because the archive has none (pack 02 §B.5).
- **"The skeptic trained on all prior out-of-sample calls"** — capped to the last thirteen weeks for the evaluation; the eight-year skill figures describe the uncapped version (pack 02 §B.3).
- **"The final decision component combines the gates' outputs"** — it does not combine; it checks that every approval was about this bar's candidate and composes the order (pack 01 §C.3, row 16).
- **"Exits on target rest as maker orders"** — every exit is a market sell (pack 02 §B.13).
- **"Fallbacks when the exchange cannot be reached"** — there are none left in paper mode; every failed fetch blocks (invariant 2, pack 01 §B.2). The only stale-value use is the emergency liquidation.
- **"Weekly retraining in the live system"** — the live program loads a named model and never retrains; weekly retraining is the evaluation's property (pack 02 §B.2).
- **"A soak test of weeks in paper mode"** — not yet run; it is the next stage (pack 03 §D).
- **The benchmark literature** — the findings say explicitly that no source was verified for "standard benchmark" claims (pack 03 §F claim 37); the review should cite its own.
- **The multiple-testing method** — Bonferroni over an enumerated ledger and a reported deflated Sharpe ratio; not BH-FDR, not a block bootstrap (both rejected with reasons in the spec, pack 03 §C.2).

## 7. How the eight chapters should divide the material

- **Introduction:** the question ("does a forecast survive the cost of acting on it"), the negative-result-is-valid stance, the account's real fee level, the one-paragraph description (pack 01 §B.1). No numbers beyond the fee table.
- **Literature review:** already written; apply §6.
- **Requirement analysis and specifications:** the invariants as requirements (pack 01 §B.2), the Locked Decisions as fixed parameters (pack 01 §B.3), the safety limits (pack 02 §A.7), the barrier and timing parameters (pack 02 §A.6), what is in and out of scope, the ethics and safety material (pack 01 §B.8). State each once here and refer back; the Design chapter must not restate a requirement, only cite it.
- **Methodology and system design:** the four stages and three chains, the fail-closed principle and the one override, the label definition, the walk-forward, the cost rule and hurdle, the acceptance bar and the trial ledger, the two benchmarks, the declared substitutes and why they are needed. Design decisions with their rejected alternatives (freeze vs liquidate; market vs resting exit; bucket table vs fitted spread model; Bonferroni vs bootstrap). Nothing about how any of it was tested.
- **Implementation:** the code as built — packages and line counts, the registry, the orchestrator loop, the client layer and where paper/live differ, the schema and the money rule, the reason-prose map, the recording tiers and pollers, the models' algorithms and features, one approval and one refusal as stored. The build-log findings (§5) belong here as "what building it taught", not in Testing.
- **Testing and evaluation:** method first (collection counts, kinds, mutation, reproducibility, static toolchain, the executable gates), then results (the walk-forward digest, the offline studies, the two runs with their trades and curves, the acceptance verdicts, the benchmarks). Keep every "as it will read" sentence with its token until filled.
- **Discussion:** §1's ten sentences expanded; the spread inversion and the cost-adaptive contrast interpreted; the power calculation; the circularity; the substitutes; what the runs do and do not say about each check.
- **Conclusion:** the contribution paragraph and the weakest-point paragraph from §3; the next stage as future work (pack 03 §D), with the warning from the findings' future-work section that nothing proposed after seeing results may be acted on without pre-declaration.
- **Appendices:** invariants verbatim, the configuration file, the schema, the reason codes, the abbreviations, the retired vocabulary, the trial-ledger rule, the limitations table, the timeline.

A rule that keeps things said once: a fact lives in the chapter where it is *established* and elsewhere is cited by chapter and table number. The invariants are established in Requirements; the chains in Design; the loop's code in Implementation; the gate counts in Testing.

## 8. Decisions for the operator before the writer starts

1. **Whether to report tier 3 at all as a statistical result if it ends under ten trades.** Recommendation: report it as descriptive, exactly as pre-registered ("tier 3's result is descriptive"), with the acceptance verdict `too few trades`. Case against: a reader may ask why a run that cannot produce an interval was made; the answer (the deadline cut the window) must then be stated plainly.
2. **Whether to add any post-hoc statistic (a naive p, a BH-FDR q) beside the pre-registered one.** Recommendation: no; report only the pre-registered interval, the deflated Sharpe ratio and the naive standard error the module already computes. Case against: a marker may expect a conventional p-value; if so, add it in a clearly labelled post-hoc paragraph and never in the results table.
3. **Whether to wait for tier 3 to finish before drafting Testing and Discussion.** Recommendation: draft now with tokens; the run has roughly ten hours left at the observed tick cost and only its trade count and final equity change. Case against: a late burst of trades in the quiet December weeks could move the count across ten and change the verdict's reason code.
4. **Whether to run the two post-run scripts (attribution, promotion gate) before or after the writer's first draft.** Recommendation: run them on the tier 5 database now (it is final) so the writer has one complete worked example of the report format; run tier 3 when it ends. Case against: both scripts read the live database; use a backup-API snapshot as the lead did, never the live file.
5. **Whether the report claims novelty for the veto-only second model and the refusal dataset.** Recommendation: only with a literature search the writer performs and documents; the repository holds none. Case against: none — an unsupported novelty claim is a mark lost.
6. **Which of the two headline framings leads:** "an instrument that produced a null result honestly" or "a cost-adaptive system that behaved differently at two fee levels". Recommendation: the first; the second is one contrast on fourteen trades. Case against: the second is the more memorable sentence and is true as far as it goes (pack 03 §C.5 gives the safe wording).
7. **Whether to include the machine-fault account in Limitations at the length the tracker gives it.** Recommendation: yes, condensed to the four bullets the tracker itself marks as the terms to use. Case against: it reads as an excuse; the mitigation is that the tracker also states what is unaffected (no production path ever exhibited it).
8. **Whether the committed default ranking (alphabetical) is changed before the write-up.** Recommendation: leave it; the report describes the daemon as committed and the simulation as flagged, and lists the change as future work. Case against: a reader who runs the code gets a different system from the one evaluated — say so in Implementation.

## 9. Writing for a reader who is neither a trader nor a programmer

The operator's note says the report must let a non-trader, non-technical reader understand the work and the contribution. Five devices that the repository's own documents already use well and that the report should borrow:

- **Lead every mechanism with the failure it prevents.** The repository's invariants are written as "this rule exists because X would otherwise happen" (why a stale spread is "a loaded gun", why a freeze is not a liquidation). A lay reader follows a rule when they see the accident it stops.
- **One worked trade, end to end, early.** The approved STORJ tick in pack 01 §C.9 — a forecast of 1.87%, costs of 0.67%, a bar of 1.00%, a position sized so that the loss at the stop is 1% of the account, a stop 48 minutes later — is the whole system in one story. Put it in the Introduction or the start of Design, in prose, before any table.
- **Translate every percentage into dollars on the 5,000 paper account.** "Friction of 0.67%" is abstract; "each round trip costs about $22 of a $3,333 position" is not. The trade rows give the exact fees (pack 03 §B.11).
- **Name the checks by what they ask, not by their code names.** "Is the market data fresh?", "Could this pair be traded at all?", "How far will it move?", "Does that beat the costs with margin?", "Can we afford it?", "Why should we not?", "Did everyone judge the same thing?" — the overview lists the four judgement questions in exactly this form (pack 01 §B.1, "The loop", step 6). The vocabulary map in §10 gives a plain name for each.
- **Explain the acceptance bar with the worked example already in the code.** The promotion module carries a ten-trade example computed by hand: promoted at one trial, not promoted at twenty (pack 03 §C.2's source). It shows a lay reader what "widened for the number of things tried" does to a result.

## 10. A vocabulary map from the repository's words to the report's

| Repository term | Suggested report term |
|---|---|
| engine (numbered) | component; name it by its question |
| guard / opportunity / manage chain | the every-minute checks; the once-a-bar decision; the position-watching step |
| gate | a check that can refuse |
| `data_guard` | the data-freshness check |
| `scout` | the universe filter and candidate ranking |
| `prediction` / the predictor | the forecast model |
| DI / `di_refused` | the unfamiliar-conditions check |
| `anomaly` | the broken-market check |
| `order_book` | the slippage estimate |
| `cost` / the cost gate | the cost check (the bar) |
| `risk` | the sizing check |
| `adaptive_router` | the model-weighting step (inactive) |
| `skeptic` / meta-labelling | the second-opinion veto |
| `decision` | the coherence check |
| `execution` | order placement |
| `position_manager` / `exit` | position watching / selling |
| `memory` | the record keeper |
| `safety` | the circuit breaker |
| `tournament` | the model scorer and the acceptance bar |
| `backtest` / replay | the simulation |
| freeze / `close_all` | pause trading / emergency sell-everything |
| expected move | the forecast return |
| friction, hurdle, net edge | round-trip cost, the bar, forecast minus cost |
| triple barrier | the three finishing lines (target, stop, time limit) |
| walk-forward, purge, embargo | week-by-week retraining; removing rows that peek at the test week; a buffer before it |
| Brier vs base-rate Brier | forecast quality against always guessing the average |
| declared (input) | assumed from a later measurement, and labelled as such |
| paper mode | simulated money against live prices |
| tier 1 / 3 / 5 | the entry fee level / a small active account's level / a large account's level |
| the operator / the lead / agents A, B, C | the author; the build process (the report should describe the AI-assisted build as method, not as authorship) |
