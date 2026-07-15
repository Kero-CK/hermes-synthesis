# Frozen-prompt micro-test report

## Scope

- Prompt schema: `criterion_assessment.v0-microtest`
- Models: `deepseek-reasoner`, `deepseek-chat`
- Temperature: `0.0`
- Cases per model: 9
- Raw API responses persisted: 18/18
- Phase-1 `auto_excludable`: empty
- No prompt or criterion change was made after seeing any response.

The result can falsify this prompt/model combination only. It does not falsify
criterion decomposition as an architecture.

## Headline result

The v0 prompt is falsified under the pre-registered acceptance criteria.

Neither model produced the expected criterion-level `hard_fail` for any of the
three known false positives. The reasoner also produced two incorrect
`hard_fail` values on one known true positive. Evidence grounding was a second,
independent failure: all 18 responses parsed as JSON and returned every
criterion in order, but many purported verbatim spans were paraphrases or
non-contiguous composites.

| Result | deepseek-reasoner | deepseek-chat |
|---|---:|---:|
| Known false positives with expected hard-fail | 0/3 | 0/3 |
| Known true positives with no hard-fail | 2/3 | 3/3 |
| Fully valid assessments after quote verification | 3/9 | 6/9 |
| Assessments with one or more invalid quotes | 6/9 | 3/9 |

Strict case acceptance additionally required a valid assessment. Under that
rule, the reasoner passed 0/6 core cases and chat passed 2/6.

## Known false positives

### Learned prompt tuning

- Expected: `I4_PRACTITIONER` as a hard-fail.
- Reasoner: `unclear`.
- Chat: `met`.
- Neither model inferred from the supplied text that this method necessarily
  trains learned prompt parameters.

This exposes a protocol-definition gap. The abstract says “prompt tuning” but
does not explicitly describe learned parameters. With outside knowledge
forbidden, the human operational rule that learned/soft prompt tuning is not
practitioner prompting must be encoded in the protocol glossary if it is meant
to control screening.

### Agent planning

- Expected: `I1_PROMPT_TECHNIQUE` as a hard-fail.
- Both models: `met`.
- Both treated physical grounding, generation, and updating of plans as a
  concrete prompt-engineering operation.

Atomic decomposition alone did not fix the semantic boundary. The protocol
needs an operational definition stating that task-level planning or agent
orchestration is not prompt construction unless the title or abstract actually
describes prompt content, structure, sequencing, transformation, verification,
or output constraints.

### Ranking evaluation

- Pre-registered expectation: `I2_REPRODUCIBLE` as a hard-fail.
- Reasoner: `I2_REPRODUCIBLE=not_reported`, plus valid hard-fails
  `E1_NO_ACTIONABLE_TECHNIQUE`, `E3_BENCHMARK_ONLY`, and
  `E4_APPLICATION_WITHOUT_PROMPT_DETAIL`.
- Chat: `I2_REPRODUCIBLE=unclear`, no hard-fail; phase-1 route
  `needs_manual`.

The micro-test exposed an inconsistency in its own oracle: under the accepted
four-state semantics, absence of a reproducible prompt structure is
`not_reported`, not `not_met`. The citable hard-fail is the positive evidence
that the paper is an evaluation/benchmark without a transferable prompt method,
namely `E3_BENCHMARK_ONLY`. A future frozen test should register E3 as the
expected criterion rather than rewriting this completed run.

## Known true positives

- Chat produced no hard-fail on all three selected true positives. Two were
  fully valid; one contained an invalid evidence span.
- Reasoner produced no hard-fail on two of three, but their assessments also
  contained invalid spans.
- On the low-resource prompting evaluation, reasoner emitted the incorrect
  hard-fails `I2_REPRODUCIBLE` and `E3_BENCHMARK_ONLY`.

The empty phase-1 `auto_excludable` policy contained this error: the candidate
route was manual rather than automatic exclusion. This demonstrates the value
of separating assessment from routing, while also showing why no phase-2
permission should be granted from this run.

## State and title-only coverage

- Reasoner used both `unclear` and `not_reported` on the title-only projections;
  both routed to `needs_manual`.
- Chat used `unclear` but no `not_reported`; it tended to mark exclusion
  criteria `not_met` from title-only evidence where the safer epistemic state
  could be `not_reported`.
- The full-abstract AI-literacy boundary case produced hard-fails rather than
  `unclear` on both models. Reasoner evidence was invalid; chat evidence was
  mechanically valid.

The fourth state is useful, but its distinction from `unclear` and unsupported
negative claims is not reliably elicited by definitions alone.

## Evidence-grounding failure

All schema, criterion coverage, and ordering checks passed. Validation failures
were quote failures: the models often shortened, joined, or lightly paraphrased
source text while presenting it as verbatim. The reasoner failed this contract
more often than chat.

This is a substantive audit failure, not cosmetic formatting. A subsequent
prompt hypothesis should test an evidence-first operation with mechanically
addressable spans, for example exact source spans selected before status
classification. That would be a new frozen prompt and a new run, not a repair
of this result.

## Decision

- Do not implement the v0 prompt in production.
- Preserve this run as a negative result.
- Keep phase 1 free of criterion-level gold re-annotation.
- Before a v1 test, clarify the protocol's domain boundaries for learned prompt
  tuning and agent planning, correct the ranking-case oracle to E3, and redesign
  evidence selection so exact grounding is the first operation.
- Phase 2 remains gated on human verification of produced hard-fails only.
