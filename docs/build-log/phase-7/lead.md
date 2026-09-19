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
