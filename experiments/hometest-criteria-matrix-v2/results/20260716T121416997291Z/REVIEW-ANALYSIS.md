# Review analysis — v2 micro-test (supplement to v2_report.md)

Verdict confirmed: **v2 falsified** under the preregistered criteria
(a, b, d, f fail; c, e pass). Per the charter discipline, no repair: the
findings below are inputs for a frozen v3.

## Where the failures actually come from

1. **The primary disease is ~85% cured but not eradicated.**
   `requires evidence` fell from 13 errors / 40 assessments (v1 calibration)
   to 2 errors / 66 assessments, both in a single case-replicate
   (gold_023.r1). The §2.2/§2.3 fixes work; criterion (a) demanded zero.

2. **The error mass was displaced, not removed — new dominant mode:
   source mislabeling.** 22 quote-grounding errors now dominate (b).
   Sampled failures show a specific pattern: the model cites the TITLE
   text verbatim but labels the evidence source `S1` instead of `T`
   (e.g. tp_cot_counterfactual, both replicates, three criteria). Forced
   by the new rule to provide a contradicting span for non-applicable
   exclusions, the model grabs the most global span available — the title
   — and mislabels it. The citation itself is faithful; the pointer is
   wrong. This is a well-defined, mechanically detectable failure mode.

3. **The E4 glossary works in expectation but not per replicate.**
   gold_033 is clean in both replicates (E4=met in the v1 calibration).
   gold_036/038/039/040 fired E4 in replicate 1 only — zero violations
   reproduced across both replicates. Under the replicate-reproduction
   policy rule, no spurious E4 auto-exclusion would have fired; the
   preregistered criterion (d) was strict per-replicate, so it fails.

4. **Stability (f): 51.5% identical hard-fail sets across replicates.**
   Far below the 90% indicative threshold. Per the charter, replicate
   reproduction before any auto-exclusion is now PERMANENTLY mandatory
   in the screening policy, for every criterion and every version.

5. **Safety held everywhere, including the true held-out.** Zero valid
   include record with a hard-fail (e), zero exclude routed include, and
   on bloc D (5 fresh records labeled before the run): all include-labeled
   records routed needs_manual or invalid, never auto-include; one
   exclude-labeled record (blocD_004) produced E1+E4 reproduced across
   both replicates.

## Registered v3 inputs

1. Source-labeling fix: an explicit prompt rule that title quotes must use
   source `T` (with the existing example made unambiguous), and/or a
   distinct validator message separating "quote found in another source"
   from "quote not found anywhere" to keep the audit trail precise.
2. Align criterion (d)-style checks with policy semantics: judge
   spurious hard-fails on reproduced-across-replicates hard-fails, since
   that is what production uses.
3. Keep the §2.1 E4 glossary and §2.2/§2.3 rules unchanged: they moved
   their targets in the right direction and are not the residual problem.
4. Consider n=3 replicates for stability estimation (cost remains cents).
