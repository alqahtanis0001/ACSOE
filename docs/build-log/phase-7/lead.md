# Phase 7 — lead

### Findings document before specs, and three claims corrected while writing it

**What happened.** The operator asked for `docs/dataset/phase-7-findings.md` before the specs: every
measured figure about the system's economics, with the simulation's slots marked, and nothing newly
measured. Three claims in the request, two of them first made by the lead, did not survive being
checked against their sources.

1. **"1 trade against 15 before friction"** (uncapped against capped skeptic). The run behind it
   (`q_funnel.out`, alphabetical, total friction 0.60%) charged tier-3 reference fees at zero
   spread. It is *after fees, before spread*. Corrected in the document.
2. **"The model's most confident calls are its most overconfident."** Nothing measured
   overconfidence by confidence level. The measured statement is narrower: over the full span, the
   calls that clear the 1.50% bar realised +0.32%. In the 1.5-year window the same selection
   realised +1.25%. The comparative claim is marked NOT MEASURED.
3. **"The simpler assumption inverted the sign."** True of the point estimate in seven of the eight
   matched cells that traded; the eighth (fees 0.50%, 6 months) went +0.43% to +0.06%. The two arms
   also differ in slippage, not only spread. The document states both.

Also found: **the funnel over the full 405-fold span was never computed past the cost stage**, so
that slot is NOT MEASURED. And **the tier-4 and tier-5 fee marks (0.55%, 0.45%) are the operator's
figures with no source on disk**; the document labels them so until the schedule fixture lands.

**Why it matters.** The chapter will be written from this document today. A claim that outruns its
source is the shape this project has caught in criteria for six phases, and a dissertation
paragraph is harder to recall than a criterion.

**Fix.** The document cites the file behind every figure. The reconnaissance scripts and their raw
outputs are committed beside it (`docs/dataset/phase-7-recon-2026-09-19/`), with terminal-only
outputs transcribed verbatim rather than re-run.

### Decision: the specs carry eight open rulings rather than defaults

**Decision.** Specs 126–143 were written with R1–R4 and R7–R10 marked RULING REQUIRED, each with the
lead's recommendation, instead of writing the recommendation in as if ruled.

*Rejected:* writing each recommendation in as the default, and letting the operator overturn it.

*Why:* R1 (the ranking) and R2 (the skeptic variant) change what the simulation measures by a factor
of four to fifteen in trade count (`phase-7-findings.md` §4, §5a). R8 to R10 define what the
evaluation's headline numbers mean. None of these is an engineering default.

*Objection:* the specs cannot all be claimed on approval. Specs 136, 138 and 139 stay held until
their rulings land, and B has one task. This is a plan with visible gaps rather than a complete one.

### The $60 figure: the operator's arithmetic holds as an upper bound, and tier 2 lowers it

**Agent:** Lead · **Date:** 2026-09-19

**What happened.** The lead and the operator disagreed about what the $60 figure for reaching tier 3
measures. The operator's arithmetic: a $1,000 balance bought and sold back generates $2,000 of
volume per round trip. At 1.20% round trip that costs about $12 in fees, so five round trips reach
$10,000 of volume for about $60 in fees. **The $60 is the fee cost of reaching tier 3, not the
volume.** That is right, and the figure had gone missing from the findings.

**Why it is an upper bound.** The arithmetic charges every trade at tier 1. The committed schedule
(`tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`) has a tier 2 from $2,500 of 30-day
volume, at 0.30%/0.60%. If the account is re-tiered as the volume accrues, the first $2,500 costs
$15 and the other $7,500 costs $33.75, about $49 in all. How quickly Kraken re-tiers is not on disk,
so the findings state $49 to $60. The cost is the volume times the average fee per side, so it does
not depend on the balance. It excludes the spread on the taker exits and the price risk while
holding.

**Fix.** Restored in `phase-7-findings.md` §R.1, with the wording that it is the fee cost made
explicit, and both figures shown.

### The seven rulings applied, and three things found while applying them

**Agent:** Lead · **Date:** 2026-09-19

R2, R4, R8, R9, R10b, R11 and R12 were written into specs 126 and 129–144, the task list, the
findings (§R.2, §R.4 to §R.9) and the tracker. Spec 75 is recorded as resolved in the tracker and in
the spec file. Three things surfaced while writing them in:

1. **Specs 135 and 136 could not both be built as written.** Spec 136 wrote the capped skeptic
   "into spec 135's run directory and manifest". But spec 135 creates that directory through
   `new_model_run_dir`, which refuses an existing directory, and its manifest carries a sha256 per
   file. A skeptic added afterwards is either refused or not covered by the manifest. **Fixed in the
   specs:** 136 writes to a staging directory, and 135's assembly runs after it, writing each run
   directory once and complete. A fold with no capped skeptic is refused, never assembled with the
   uncapped one.
2. **R4 and "alphabetical as the baseline" together make four runs, not two.** Spec 143 described
   one run per tier. It now describes two rankings at two tiers, with the tiers in parallel and the
   folds in sequence within each run.
3. **R10b's working form still left two choices open**: which overlap-robust interval, and how
   "widened for trials" is computed. Leaving them to the builder would mean choosing them after the
   code exists and closer to a result. **Chose, in spec 139:** HAC (Newey–West) on the per-trade
   series, with the lag set to the largest number of trades overlapping any one hold, computed from
   times alone; and Bonferroni over the ledger's trial count.
   *Rejected:* a block bootstrap (coarse at tens of trades, and it adds a seed and a resample count),
   and the deflated Sharpe ratio's expected-maximum offset (it needs a variance of Sharpe ratios
   across trials, which most ledger rows cannot supply). **Contestable, so it is flagged to the
   operator with the specs rather than settled silently.**

One reading is also flagged rather than assumed. R8's second benchmark is taken as the recommendation
worded it: the pairs held, **while** they were held, and cash otherwise. The other reading, the held
pairs bought and held over the whole window, would be a third series, not a replacement.
