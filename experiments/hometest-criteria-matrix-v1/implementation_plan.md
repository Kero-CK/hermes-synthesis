# Implementation plan

## Scope

Create the v1 screening experiment exclusively under this directory. The v0
experiment and production files remain read-only. No LLM API call and no git
commit are part of this implementation.

## Files

- `[NEW] prompt.txt`: frozen v1 prompt, copied verbatim from the specification.
- `[NEW] criteria.json`: v0 criteria with only the schema changed to
  `screening_criteria.v1-microtest`.
- `[NEW] run_microtest.py`: v1 harness with sentence-indexed documents,
  normalized sentence-local evidence validation, duplicate-key rejection,
  coherence checks, v1 oracle alternatives, held-out selection, manifest
  provenance, and API-free dry-run mode.
- `[NEW] PREREGISTRATION.md`: complete oracle, selection rule, matcher,
  coherence rules, and verbatim success/failure criteria.
- `[NEW] test_microtest_v1.py`: direct-executable unit tests for the matcher,
  sentence segmentation, parser, coherence rules, and held-out selection.
- `[NEW] replay_v0_quotes.py`: v0 full-document quote-regression comparison
  using the v1 normalizer only for the after count.
- `[NEW] DEVIATIONS.md`: recorded interpretations, environment limitations,
  test outputs, and replay output.

## Verification

Run the direct unit test module, run `run_microtest.py --dry-run` with the
available fixture when the configured review directory is unavailable, run
the v0 quote replay, and inspect git status to confirm that only this v1
directory was created.
