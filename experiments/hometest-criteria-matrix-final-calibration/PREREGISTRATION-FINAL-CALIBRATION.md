# PREREGISTRATION — terminal assisted criteria-matrix calibration

This document freezes the terminal calibration before any API call. It is a
measurement and policy-anchoring phase, not a prompt optimization. No
post-observation change is permitted.

## Frozen inputs

- Corpus: the exact bytes of
  `../hometest-criteria-matrix-v1-calibration/results/20260715T161454171501Z/cases.jsonl`.
- Corpus SHA-256:
  `70dff2678d974883126b480c4b2884ed2b1da059598b3f7f235972e58935b7cf`.
- Prompt: the existing v3 prompt, imported by the v3 harness and unchanged.
- v3 system-prompt SHA-256:
  `b723fbb068da8eefec9d77cfa162d2090ee680676ace3b9b5c1b2614d8c0c047`.
- Criteria SHA-256:
  `41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21`.
- Requested model: `deepseek-reasoner`.
- Temperature: `0`.
- Replicates: `n=2` per case.
- Expected corpus: 40 unique cases and 80 attempted call slots.

The runner performs the historical v1 reference-manifest check, the v2 base
prompt anchor check, the v3 prompt-delta check, and the exact corpus hash
check before either dry-run processing or a real run.

## Terminal policy

- The only permitted allowlist member is `I1_PROMPT_TECHNIQUE`.
- A pair is exploitable only when both replicates are present, valid, and
  have no coherence error.
- A hard-fail is reproduced only when it occurs in both valid replicates of
  the same case.
- Only a reproduced I1 hard-fail on an exclude-labeled, non-title-only case
  can create a proposal.
- Every I1 proposal is exactly `needs_human_validation`; the runner never
  emits `exclude_final`.
- A single valid replicate, a divergence, an invalid assessment, a technical
  error, a title-only case, or any observed hard-fail other than I1 routes to
  a human and cannot create a proposal.
- A reproduced I1 on an include-labeled case is a safety violation and is
  never a proposal.
- Human validation has priority and is recorded in a deterministic checklist.
- The final allowlist remains pending until that checklist is completed. If
  I1 is disqualified for safety, the only allowed final allowlist is empty.
- E2, E4, I4, and every criterion other than I1 are descriptive and cannot
  extend the allowlist.

## Rules 1–3 measurement

The historical Rules 1–3 are applied only to `I1_PROMPT_TECHNIQUE` and only
to reproduced hard-fails in this exact 40-case terminal corpus. Rule 1 checks
valid include pairs; Rule 2 counts unique DOI support among valid exclude
pairs; Rule 3 selects at most five exclude DOI instances deterministically by
`sha256(doi.lower() + ":" + criterion_id)`. No final allowlist decision is
made before the human checklist is filled.

## Model identity

The requested model and every `model` identifier returned by the API are
recorded as separate manifest fields. A returned model identifier is never
silently rewritten to the requested identifier.

## Closure

`terminal_calibration: true` and `prompt_optimization_closed: true` are
recorded in every manifest. The v3 result remains a falsified, auditable
reference; this phase does not authorize a v4 or any later prompt iteration.
