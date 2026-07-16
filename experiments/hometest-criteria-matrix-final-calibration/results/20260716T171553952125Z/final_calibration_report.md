# Terminal assisted calibration report

Results directory: `C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-final-calibration\results\20260716T171553952125Z`

This report is offline-only. It performs no API calls and makes no
final allowlist decision before human verification.

## Frozen coverage and model identity

- Cases: 40/40.
- Assessment lines: 80/80.
- Pair summaries: 40; valid comparable pairs: 0.
- Requested model: `deepseek-reasoner`.
- Returned model identifiers: aucun identifiant de modèle retourné n’a été observé (manifest response_models=[]).
- Requested and response model identifiers are not conflated.
- Prompt SHA-256: `b723fbb068da8eefec9d77cfa162d2090ee680676ace3b9b5c1b2614d8c0c047`.
- Criteria SHA-256: `41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21`.
- Corpus SHA-256: `70dff2678d974883126b480c4b2884ed2b1da059598b3f7f235972e58935b7cf`.
- Anchor commit: `4491e03522e24a0c1e9a6773d3d967928c8a74a6`.

## Coverage and errors

| Replicate | Records | Invalid | Technical | Rate |
|---:|---:|---:|---:|---:|
| 1 | 40 | 40 | 40 | 100.0% |
| 2 | 40 | 40 | 40 | 100.0% |
| ALL | 80 | 80 | 80 | 100.0% |

| Error class | Count |
|---|---:|
| requires-evidence | 0 |
| source-label mismatch | 0 |
| grounding | 0 |
| coherence | 0 |
| technical | 80 |
| schema | 0 |
| other validation | 0 |

## Replicate stability

- Global hard-fail stability: 0/0 valid pairs (0.0%).
- I1-specific stability: 0/0 valid pairs (0.0%).
- Incomplete or invalid pairs: 40.

## Reproduced hard-fails by human label

| Criterion | Include | Exclude | Other |
|---|---:|---:|---:|
| I1_PROMPT_TECHNIQUE | 0 | 0 | 0 |

## Reproduced I1 support

- Include pairs carrying reproduced I1: none.
- Exclude occurrences carrying reproduced I1: 0.
- Exclude unique DOI support: 0.
- Exclude case IDs: none.

## Assisted I1-only policy simulation

- Allowlist under measurement: {I1_PROMPT_TECHNIQUE}.
- Proposals: 0/40 cases (0.0%).
- Proposals among valid exclude pairs: 0/0 (0.0%).
- Routed to human: 40/40 (100.0%).
- Reproduced I1 include safety violations: 0.
- Potential false-negative routing cases: 18.
- Every proposal remains `needs_human_validation`; `exclude_final` is forbidden.

### Proposed I1 exclusions

None.

### Safety violations

None.

## Historical Rules 1–3, I1 and reproduced pairs only

- Rule 1/2 status: `not_qualified` — Rule 2: fewer than 3 unique exclude DOIs carry reproduced I1 in the terminal corpus.
- Rule 2 unique DOI support: 0 (minimum 3).
- Rule 3 sample size: 0.
- Final allowlist status: `pending_human_checklist`.
- No E2, E4, I4, or other criterion can extend the allowlist.

## Residual v3 limits

- v3 remains falsified: (a) and (g) passed; (b)–(f) failed.
- v3 produced 14/62 invalid assessments and one reproduced E4 violation.
- `blocD_005` reproduced E1 and E4 on an include label but did not reproduce I1; it remains a human case under the terminal policy.
- No I1 hard-fail was reproduced in the v3 corpus.

## Human verification gate

The accompanying checklist must be completed before any final
allowlist decision. A refusal disqualifies I1; no checklist entry
can authorize a criterion other than I1.
