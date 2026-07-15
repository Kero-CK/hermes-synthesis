# Calibration report — criteria-matrix v1

Results directory: `results\20260715T161454171501Z`

This report is offline-only. It does not call an API and does not alter the frozen v1 harness.

## Route distribution

| Label | Records | include | needs_manual | invalid_assessment | technical_error |
|---|---:|---:|---:|---:|---:|
| all | 40 | 16 | 11 | 13 | 0 |
| include | 22 | 16 | 1 | 5 | 0 |
| exclude | 18 | 0 | 10 | 8 | 0 |

## Invalid assessments and error taxonomy

Invalid assessments: 13/40 (32.5%).

| Error class | Count |
|---|---:|
| coherence | 4 |
| quote/evidence grounding | 6 |
| requires evidence | 13 |

The `requires evidence` count is reported separately because it is a registered v2 input.

## Hard-fails by criterion and label

| Criterion | include valid | include invalid | exclude valid | exclude invalid |
|---|---:|---:|---:|---:|
| E1_NO_ACTIONABLE_TECHNIQUE | 1 | 2 | 9 | 8 |
| E2_MODEL_TRAINING_ONLY | 0 | 0 | 0 | 2 |
| E3_BENCHMARK_ONLY | 0 | 0 | 2 | 0 |
| E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 0 | 0 | 6 | 5 |
| E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE | 1 | 2 | 7 | 2 |
| I1_PROMPT_TECHNIQUE | 0 | 1 | 3 | 4 |
| I2_REPRODUCIBLE | 0 | 1 | 3 | 4 |
| I3_LLM_TARGET | 0 | 0 | 1 | 0 |
| I4_PRACTITIONER | 0 | 0 | 1 | 2 |
| I5_ENGLISH | 0 | 0 | 0 | 0 |
| I6_AFTER_2020 | 0 | 0 | 0 | 0 |

## Candidate criteria: Rules 1 and 2

Règle 1 (disqualification mécanique) : un critère candidat X est disqualifié si X apparaît dans les hard_fails d'AU MOINS UN record labellisé include avec assessment valide (zéro validation_error, zéro coherence_error).

Règle 2 (support minimal) : X doit être un hard-fail sur au moins 3 DOI uniques labellisés exclude avec assessment valide, en cumulant micro-test v1 et calibration (un même DOI présent dans les deux corpus ou sous plusieurs variantes ne compte qu'une fois).

| Criterion | Status | Valid include hits | Calibration exclude support (occurrences) | Micro-test exclude support (occurrences) | Unique DOI support | Total support (occurrences) | Reason |
|---|---|---:|---:|---:|---:|---:|---|
| E1_NO_ACTIONABLE_TECHNIQUE | disqualified | 1 | 9 | 4 | 11 | 13 | Rule 1: valid include record contains this hard-fail. |
| E2_MODEL_TRAINING_ONLY | not_qualified | 0 | 0 | 2 | 2 | 2 | Rule 2: only 2 unique DOI(s) support this hard-fail on valid exclude records; at least 3 required. |
| E4_APPLICATION_WITHOUT_PROMPT_DETAIL | qualified | 0 | 6 | 3 | 8 | 9 | Rules 1 and 2 passed. |
| E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE | disqualified | 1 | 7 | 2 | 8 | 9 | Rule 1: valid include record contains this hard-fail. |
| I1_PROMPT_TECHNIQUE | qualified | 0 | 3 | 2 | 5 | 5 | Rules 1 and 2 passed. |
| I4_PRACTITIONER | qualified | 0 | 1 | 3 | 3 | 4 | Rules 1 and 2 passed. |

Blocked regardless of measurement: `I2_REPRODUCIBLE` and `E3_BENCHMARK_ONLY`.

## Rule 3 sampling

Règle 3 (vérification humaine échantillonnée) : pour chaque X encore qualifié, échantillon d'au plus 5 instances de hard-fail sur des records exclude avec assessment valide, hors les 7 DOI du micro-test (déjà vérifiés en phase 2) ; sélection déterministe par tri croissant de sha256(doi_minuscule + ":" + criterion_id). Exigence : 100 % de CONFIRMÉ sur l'échantillon — un seul REFUSÉ retire X de la allowlist jusqu'au v2.

| Criterion | Qualified for sampling | Sample size | Case IDs |
|---|---|---:|---|
| E1_NO_ACTIONABLE_TECHNIQUE | False | 0 |  |
| E2_MODEL_TRAINING_ONLY | False | 0 |  |
| E4_APPLICATION_WITHOUT_PROMPT_DETAIL | True | 5 | gold_038, gold_039, gold_040, gold_033, gold_036 |
| E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE | False | 0 |  |
| I1_PROMPT_TECHNIQUE | True | 3 | gold_031, gold_033, gold_039 |
| I4_PRACTITIONER | True | 1 | gold_031 |

The generated `phase2_sample_checklist.md` contains the empty human-verdict fields.

## Allowlist simulation

Simulated allowlist: E4_APPLICATION_WITHOUT_PROMPT_DETAIL, I1_PROMPT_TECHNIQUE, I4_PRACTITIONER.
Valid exclude records routed `exclude`: 7/10 (70.0%).
Valid include records routed `exclude`: 0/17.

| Metric | Value |
|---|---:|
| Valid exclude records | 10 |
| Auto-excluded exclude records | 7 |
| Automation rate | 70.0% |
| Include records auto-excluded | 0 |

## Signal d'alerte

Hard-fails on include records with invalid assessments are reported but do not disqualify a criterion:

| Criterion | Count | Case IDs |
|---|---:|---|
| E1_NO_ACTIONABLE_TECHNIQUE | 2 | gold_007, gold_026 |
| E2_MODEL_TRAINING_ONLY | 0 |  |
| E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 0 |  |
| E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE | 2 | gold_007, gold_026 |
| I1_PROMPT_TECHNIQUE | 1 | gold_026 |
| I4_PRACTITIONER | 0 |  |

## Stratification

### By stratum

| stratum | Records | Include | Exclude | Valid | Invalid | Include route | Manual route | Invalid route |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 40 | 22 | 18 | 27 | 13 | 16 | 11 | 13 |

### By abstract source

| abstract_source_original | Records | Include | Exclude | Valid | Invalid | Include route | Manual route | Invalid route |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| openalex | 40 | 22 | 18 | 27 | 13 | 16 | 11 | 13 |

## Frozen rules

I2 and E3 remain excluded from any auto_excludable allowlist, and no prompt, criteria, matcher, or rule was changed after observation.
