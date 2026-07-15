# Deviations and verification — v1 calibration

## Interpretations

- The calibration harness consumes every row of `gold_set.csv` in source order and assigns `gold_001` through `gold_040` for the real review directory. The fixture remains available for direct tests and contains 24 rows.
- The v1 `holdout_selection_rule` is retained verbatim in the calibration manifest for schema compatibility, but it is not applied because calibration uses the complete gold set.
- The frozen prompt and criteria are loaded from `../hometest-criteria-matrix-v1`; no prompt, criteria, matcher, or v1 validation implementation is copied into this directory.
- `AUTO_EXCLUDABLE` is empty. Rules 1 and 2 are measured offline from valid assessments, and Rule 3 produces a deterministic human-verification checklist rather than an automatic allowlist decision.
- Rule 1 is applied to valid calibration records labelled `include`; Rule 2 combines valid `exclude` hard-fail records from calibration and the v1 reasoner assessment, but qualifies on the union of canonical unique DOIs. Occurrence counters remain informative only. Rule 3 removes all seven micro-test DOIs before deterministic sampling.
- The reference manifest's `prompt_sha256` and `criteria_sha256` are treated as the frozen integrity hashes. A mismatch raises the required `frozen prompt integrity check failed` error before artifact generation.

## Exact test output

Command:

```text
PYTHONDONTWRITEBYTECODE=1 python test_calibration.py
```

Output:

```text
.....
----------------------------------------------------------------------
Ran 5 tests in 0.055s

OK
```

## Exact real-review dry-run output

Command:

```text
PYTHONDONTWRITEBYTECODE=1 python run_calibration.py --dry-run --review-dir "C:\Users\cedri\Documents\Work\Obsidian\Hermes\Projets\Hermes Synthesis\Reviews\hometest-prompteng"
```

Output:

```text
FROZEN_PROMPT_INTEGRITY=PASS
PROMPT_SHA256=eab475df17a7247e8ab9d3ee0648864849a8cf84e1d437147531d5267a633698
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v1-calibration\dryrun\20260715T155851675413Z
VALIDATOR_SELF_TEST=PASS
CASES=40
```

The dry-run wrote `cases.jsonl`, `user_messages.jsonl`, `run_manifest.json`, and `validator_self_test.json` below the calibration directory. It made no API call.

## Exact fixture dry-run output

Command:

```text
PYTHONDONTWRITEBYTECODE=1 python run_calibration.py --dry-run --review-dir "..\..\examples\calib-selfimprove"
```

Output:

```text
FROZEN_PROMPT_INTEGRITY=PASS
PROMPT_SHA256=eab475df17a7247e8ab9d3ee0648864849a8cf84e1d437147531d5267a633698
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v1-calibration\dryrun\20260715T155851654030Z
VALIDATOR_SELF_TEST=PASS
CASES=24
```

This fixture dry-run also made no API call.

## Amendement Règle 2

The Rule 2 amendment was applied before any calibration API call. Decision support now uses the union of canonical unique DOI values across valid exclude records from calibration and the v1 reasoner assessment; occurrence counters remain in the analysis output for transparency.

Exact test command and output:

```text
PYTHONDONTWRITEBYTECODE=1 python test_calibration.py
.....
----------------------------------------------------------------------
Ran 5 tests in 0.144s

OK
```

Exact real-review dry-run command and output:

```text
PYTHONDONTWRITEBYTECODE=1 python run_calibration.py --dry-run --review-dir "C:\Users\cedri\Documents\Work\Obsidian\Hermes\Projets\Hermes Synthesis\Reviews\hometest-prompteng"
FROZEN_PROMPT_INTEGRITY=PASS
PROMPT_SHA256=eab475df17a7247e8ab9d3ee0648864849a8cf84e1d437147531d5267a633698
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v1-calibration\dryrun\20260715T160753133451Z
VALIDATOR_SELF_TEST=PASS
CASES=40
```

## Scope verification

The implementation files, tests, documentation, and dry-run artifacts are all under `experiments/hometest-criteria-matrix-v1-calibration/`. The v1 directory and all files outside the calibration directory were left unchanged. No files were staged and no commit was created.
