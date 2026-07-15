# Frozen-prompt v1 micro-test report

## Scope

- Prompt schema: `criterion_assessment.v1-microtest`
- Models: `deepseek-reasoner`, `deepseek-chat`
- Temperature: `0.0`
- Cases per model: 15 (9 core + 6 deterministic held-out)
- Raw API responses persisted: 30/30
- Phase-1 `auto_excludable`: empty
- Preregistration anchored at commit `3b171e9` before the run; no prompt,
  criterion, oracle, or matcher change was made after seeing any response.
- A first launch attempt failed with HTTP 401 on all 30 calls (invalid API
  key, directory `results/20260715T134952662934Z`); no response was received
  and no result was produced. The key was replaced and this run is the first
  and only complete execution of the frozen v1 test.

## Headline result

**deepseek-reasoner passes all five preregistered criteria. deepseek-chat is
falsified on criteria (b) and (e).**

| Preregistered criterion | deepseek-reasoner | deepseek-chat |
|---|---:|---:|
| (a) Evidence items mechanically valid (≥ 95%) | 146/146 = 100% ✅ | 148/149 = 99.3% ✅ |
| (b) Primary-or-alternative hard-fail on known FPs (≥ 2/3) | 2/3 ✅ | 0/3 ❌ |
| (c) False hard-fails on include-labeled cases (must be 0) | 0 ✅ | 0 ✅ |
| (d) Coherence errors in valid assessments (must be 0) | 0 ✅ | 0 ✅ |
| (e) Exclude-labeled cases routed `include` (must be none) | none ✅ | `fp_prompt_tuning` ❌ |

## What the v1 interventions fixed

- **Sentence-indexed evidence eliminated the grounding failure.** The v0
  reasoner produced invalid quotes in 6/9 assessments (paraphrases, splices,
  smoothing). Under the v1 contract it produced 146/146 mechanically valid
  evidence items. The failure mode did not shrink; it disappeared.
- **The protocol glossary produced the prompt-tuning exclusion.** The reasoner
  returned `I4_PRACTITIONER=not_met` and `E2_MODEL_TRAINING_ONLY=met` on
  `fp_prompt_tuning`, citing the learned-parameter definition and noting that
  no statement marks the prompts as discrete or manual. This is exactly the
  registered primary plus its accepted alternative.
- **Decision D separated the minimal pair.** In v0 the reasoner emitted false
  hard-fails (`I2`, `E3`) on the included evaluation paper
  `tp_low_resource_prompting`. In v1 it routes that paper `include` with
  `I2=met`, explicitly reasoning that named prompting families count as
  transferable methods, while still hard-failing the excluded ranking paper
  through `E3` + `E1` + `E4`.
- **Held-out generalization.** All six held-out cases behaved correctly for
  the reasoner where assessments were valid: three excluded papers (a
  healthcare prompting survey, the RLHF training paper, an agents survey)
  produced dense, citable hard-fails and routed `needs_manual`; two of three
  included papers routed `include` cleanly.

## Residual defects

- **Reasoner: `not_met` without evidence on non-applicable exclusions.** In
  3/15 cases (`tp_cot_counterfactual`, `state_boundary_ai_literacy`,
  `holdout_include_1`) the reasoner marked exclusion criteria `not_met` with
  an empty evidence array where the tie-breaker demands `not_reported`. The
  v0 disease (fabricated quotes) is gone; its replacement (wrong state, no
  fabrication) is mechanically caught and routed `invalid_assessment`, so it
  costs retries or manual review, never a wrong decision. This is the single
  v2 target.
- **Reasoner: `fp_agent_planning` still misses the registered oracle.** It
  produced `E4=met` (not registered for this case) instead of `I1`/`E1`.
  Note `I1` moved from `met` (v0) to `unclear` (v1) under the
  mechanism-vs-use rule, and the case routes `needs_manual`. Safe outcome,
  oracle miss; within the 2/3 threshold.
- **Chat: the glossary was ignored.** On `fp_prompt_tuning` chat asserted
  `I4=met` ("applicable by practitioners without training model weights") in
  direct contradiction with the supplied protocol definition, marked every
  inclusion `met`, and produced the run's only `include` route on a
  human-excluded article. Chat's near-perfect evidence fidelity makes this
  failure clean, confident, and mechanically invisible — the exact risk
  profile phase-1 screening cannot tolerate.

## Decision

- The v1 prompt/protocol combination is **not falsified for
  deepseek-reasoner** and is **falsified for deepseek-chat**.
- deepseek-reasoner becomes the production candidate for criterion-level
  screening; deepseek-chat is rejected in this role.
- Phase 2 now applies: human verification of the 20 hard-fails produced by
  the reasoner on valid assessments (7 articles), listed in
  `phase2_checklist.md`. No `auto_excludable` permission is granted until
  that verification is complete.
- The v2 iteration (new frozen prompt, new run) should target the single
  residual reasoner defect: `not_met` with empty evidence on non-applicable
  exclusion criteria, where `not_reported` is required.
