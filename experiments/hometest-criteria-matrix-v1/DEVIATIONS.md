# Deviations and implementation notes

## Interpretations

- `cases.jsonl.sentences` is represented as an ordered list of objects with
  `source` (`S1`, `S2`, …) and exact sentence `text`. This makes the persisted
  source-to-text mapping explicit while keeping sentence-local validation
  deterministic.
- An empty abstract produces no `S` line in the user message. Title-only
  projections therefore contain only `T` and persist `"sentences": []`.
- The sentence splitter uses the specified regex verbatim and applies the
  abbreviation guard to `i.e.`, `e.g.`, and `etc.` immediately before a
  candidate boundary. Residual markup such as `<sup>` is retained as data;
  because `<` is in the regex lookahead, it can begin a separate indexed item.
- The v1 harness treats malformed model JSON, including duplicate JSON keys,
  as `validation_errors`, not technical failures. API/network failures remain
  technical failures.
- A validation or coherence error makes routing `invalid_assessment`. A
  coherence error also prevents acceptance. The held-out exclude rule follows
  the specification literally: any route other than `include` is accepted
  unless a coherence error is present; the other acceptance categories require
  a complete valid assessment. Boundary and title-only cases remain
  coverage-only (`acceptance: null`).

## Environment limitations

- The configured default review directory
  `/vault/Projets/Hermes Synthesis/Reviews/hometest-prompteng` is not accessible
  in this Windows workspace. The held-out selector is nevertheless implemented
  against `gold_set.csv` and the unit test uses the available
  `examples/calib-selfimprove` CSV fixture.
- No LLM API call was made and no git commit was created.

## Verification results

The following sections are filled with the exact local command outputs after
the v1 tests, dry-run, and v0 quote replay are executed.

### Unit tests

`python -m py_compile run_microtest.py test_microtest_v1.py replay_v0_quotes.py`
completed successfully.

`python test_microtest_v1.py`:

```text
........
----------------------------------------------------------------------
Ran 8 tests in 0.004s

OK
```

The prompt comparison against the attached specification returned
`prompt_exact_lf True`; the criteria comparison returned
`criteria_texts_equal True` and the v1 schema is
`screening_criteria.v1-microtest`.

### Dry-run

With the available fixture:

```text
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v1\dryrun\20260715T132401272360Z
VALIDATOR_SELF_TEST=PASS
CASES=6
```

With the configured but inaccessible default review directory:

```text
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v1\dryrun\20260715T132401372415Z
VALIDATOR_SELF_TEST=PASS
CASES=0
```

No `results/` directory was created by either dry-run. The fixture manifest
contains the sentence regex, matcher specification, coherence rules, held-out
selection rule, oracle, and the current `git rev-parse HEAD` value.

### v0 quote replay

`python replay_v0_quotes.py`:

```text
deepseek-chat: before=6/9 after=7/9
deepseek-reasoner: before=3/9 after=5/9
```

These values match the registered expectation; no matcher adjustment was made
to force the result.

### Repository-scope check

The v1 directory contains the seven requested deliverables plus the
implementation plan and dry-run artifacts. `Test-Path experiments/hometest-criteria-matrix-v1/results`
returned `False`. The v0 directory and production files were left unchanged;
the final status inspection showed only the pre-existing workspace files and
the new v1 files as untracked. No commit was created.
