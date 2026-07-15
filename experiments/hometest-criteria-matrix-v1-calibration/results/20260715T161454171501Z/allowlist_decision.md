# Allowlist decision — auto_excludable, criteria-matrix v1

## Sealed decision

**`auto_excludable` = { `I1_PROMPT_TECHNIQUE` }**

Scope of validity (per the locked policy/protocol separation): model
`deepseek-reasoner`, frozen v1 prompt (`eab475df17a7…`), frozen v1 criteria
(`41ddfe013dd6…`), calibration run `20260715T161454171501Z`, human phase-2
verifications of 2026-07-15. Any change to model, prompt, criteria, or
matcher voids this allowlist.

## Rule outcomes

| Criterion | R1 (include hit) | R2 (unique DOIs ≥ 3) | R3 (human sample) | Result |
|---|---|---|---|---|
| E1 | failed (gold_025) | — | — | out |
| E2 | passed | failed (2) | — | out (insufficient data) |
| E4 | passed | passed (8) | **0/5 confirmed** | out |
| E5 | failed (gold_025) | — | — | out |
| I1 | passed | passed (5) | **3/3 confirmed** | **in** |
| I4 | passed | passed (3) | 0/1 confirmed | out |
| I2, E3 | barred a priori (micro-test phase 2) | | | out |

R3 refusal patterns: E4 systematically over-applied to multi-application
surveys, systems/privacy frameworks, and evaluation perspectives — none of
which are "a domain application of an LLM"; I4 `not_met` asserted where no
technique exists to qualify (the `not_met`/`not_reported` disease).

## Expected effect

On this gold set, I1 alone auto-excludes 3/10 valid exclude records
(3/18 = 17% of all excludes) and touches 0/17 valid include records. The
practical automation gain is modest; the main value of this calibration is
the negative evidence (E4, I4, E1, E5 kept out) and the v2 target
confirmation.

## Post-hoc observation: temperature-0 instability

The DOI `10.48550/arxiv.2308.11432` was assessed twice on byte-identical
inputs (micro-test `holdout_exclude_3`, calibration `gold_033`). Three
statuses flipped between runs: I1 `not_reported`→`not_met`,
I2 `not_reported`→`not_met`, E4 `not_met`→`met`. DeepSeek temperature-0
decoding is not fully deterministic, and the instability concentrates
exactly on the `not_met`/`not_reported` boundary. Consequences:

- Decision-level safety is preserved here (both routes are non-include for
  an exclude-labeled record, and Rule 1 guards includes), so the sealed
  allowlist stands under the preregistered rules.
- Future calibrations and the v2 test should run n≥2 replicates per record
  and require hard-fail reproduction across replicates before an
  auto-exclusion fires. This requirement is registered as a v2 design input,
  not applied retroactively.

## Registered v2 inputs (from this run and its phase 2)

1. `not_met`/`not_reported` discipline (primary target): 13
   `requires evidence` validation errors, the I4 refusal, the two I2
   refusals from the micro-test phase 2, and the instability axis above.
2. E4 glossary clarification (secondary): "a domain application" means the
   article's primary contribution is applying an LLM to a specific task or
   domain; surveys, overviews of multiple applications, and
   evaluation/system frameworks are not domain applications.
3. Replicate-based stability requirement (methodological).
