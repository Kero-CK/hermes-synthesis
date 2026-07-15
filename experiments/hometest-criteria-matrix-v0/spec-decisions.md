# Locked screening-matrix decisions

This file records decisions accepted before the v0 micro-test. It is not the
full implementation specification.

## Protocol and policy separation

- The scientific protocol owns stable criterion IDs, criterion kind, atomic
  wording, and any domain definitions needed to interpret those criteria.
- Model-specific permissions such as `auto_excludable` and permission to
  auto-exclude from title-only evidence belong to a separately versioned
  screening policy tied to model, prompt, protocol hash, and calibration run.
- Conceptual title-assessability and machine authorization from title-only
  evidence are distinct properties.

## Migration

- New screening and calibration code must fail loudly on legacy flat
  protocols. It must not silently atomize or reinterpret them.
- Historical reviews remain readable and reportable without migration.
- Only a review being re-screened or recalibrated needs migration.
- `init_review.py`, `screen.py`, and `calibrate.py` must consume one canonical
  structured criterion source rather than maintaining divergent parsers.

## Evidence states

- `met`: one or more mechanically verifiable evidence spans are required.
- `not_met`: one or more mechanically verifiable evidence spans are required;
  absence of information is not `not_met`.
- `unclear`: one or more spans showing relevant but vague, partial, or
  conflicting information are required.
- `not_reported`: evidence must be empty.
- An undocumented required inclusion criterion routes to `needs_manual`.
- An undocumented exclusion criterion is simply not triggered and does not by
  itself route to `needs_manual`.

## Phasing and human annotation

- Phase 1 uses a conservative resolver with `auto_excludable` empty or minimal.
  It requires no criterion-by-criterion re-annotation of the existing gold set.
- Phase 2 human-checks only the `hard_fail` assessments actually produced by
  the model. It does not launch a 40-record-by-N-criteria annotation campaign.
- Full assessments and raw model responses must be persisted so candidate
  policies can be replayed without further LLM calls.

## Missing abstracts and publisher bias

- In the observed manifest, 32 abstracts were missing from OpenAlex and
  Crossref recovered 3 (about 9%). Crossref is an optional enrichment source,
  not a prerequisite or a general remedy.
- Missing abstracts are non-random and correlate with publisher and subject,
  including publisher text-mining restrictions. This is a methodological bias
  risk for the review, not only a workload issue.
- Reports and calibration must stratify decisions and manual-review burden by
  evidence availability and source; aggregate metrics alone can hide
  publisher-correlated selection effects.
- Hermes currently has no downstream full-text eligibility re-screening.
  `unclear` or undocumented required inclusion criteria therefore cannot be
  advanced directly into synthesis as if eligibility had been established.
