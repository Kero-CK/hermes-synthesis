# Deviations and verification — terminal assisted calibration

## Pre-run interpretations

- The frozen `cases.jsonl` is copied byte-for-byte into each run directory;
  no `bloc` field is added to the corpus file. Assessment rows use the
  manifest block name `gold_set` only for reporting compatibility.
- Rules 1–3 are evaluated on the exact terminal 40-case corpus only. The
  v3 micro-test is a separate falsified reference and is not unioned into the
  terminal support calculation; this keeps the terminal corpus and its
  preregistered 80 slots self-contained.
- The safety policy is conservative: if either valid replicate observes a
  hard-fail other than I1, the pair is routed to a human even when I1 is also
  reproduced. This avoids treating a mixed hard-fail pair as an automatic
  proposal.
- “Potential false negatives” means exclude-labeled pairs that do not produce
  a safe I1 proposal; it is a routing-risk count, not a claim that the human
  label is wrong.
- `requested_model` is the CLI model (`deepseek-reasoner` by default); raw
  response `model` values are retained and reported independently.

## Frozen v3 limits carried forward

- v3 is falsified: (a) and (g) passed; (b)–(f) failed.
- v3 had 14/62 invalid assessments.
- One E4 violation was reproduced.
- `blocD_005`, labelled include, reproduced E1 and E4.
- `blocD_005` did not reproduce I1; with I1 only it remains manual.
- No I1 hard-fail was reproduced in the v3 corpus.
- The three v3 frozen-integrity checks passed.

The committed v3 manifest/assessments preserve the model discrepancy rather
than normalizing it: the requested/assessment identifier is
`deepseek-reasoner`, while the raw response `model` field observed in the
v1-calibration, v2, and v3 runs is `deepseek-v4-flash`. The terminal runner
records both fields separately.

## Verification commands and outputs

This section is completed only with outputs actually observed during the
API-free verification. No 80-call run is permitted in this mission.

### Historical v1-calibration tests

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

### v3 regression suite

The unmodified `test_v3.py` was also run against the now-labelled real
`blocD.csv`. Its stale dry-run expectation failed exactly as follows:

```text
PROMPT_DIFF=PASS
FROZEN_INTEGRITY=PASS
SOURCE_DIAGNOSTIC=PASS
REPRODUCED_HARD_FAILS=PASS
TEST_FAILURE=unlabelled D dry-run count: expected 0, got 5
```

The v3 source was not changed. The same seven checks were rerun with an
unlabelled CSV created only in a temporary directory and injected at runtime:

```text
PROMPT_DIFF=PASS
FROZEN_INTEGRITY=PASS
SOURCE_DIAGNOSTIC=PASS
REPRODUCED_HARD_FAILS=PASS
FROZEN_BLOCKS=PASS
BLOCD_AND_REPLICATES=PASS
LABEL_HELPER=PASS
TESTS=7
ALL_TESTS=PASS
```

### Terminal calibration tests

Command:

```text
PYTHONDONTWRITEBYTECODE=1 python test_final_calibration.py
```

Output:

```text
FROZEN_V1_INTEGRITY=PASS
FROZEN_V2_BASE_INTEGRITY=PASS
FROZEN_PROMPT_INTEGRITY=PASS
FROZEN_CORPUS_INTEGRITY=PASS
V3_PROMPT_SHA256=b723fbb068da8eefec9d77cfa162d2090ee680676ace3b9b5c1b2614d8c0c047
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
CORPUS_SHA256=70dff2678d974883126b480c4b2884ed2b1da059598b3f7f235972e58935b7cf
ANCHOR_COMMIT=ffb334aa6544556f989d36493de3fc5fcbb05362
CASES=40
CALLS=80
N_REPLICATES=2
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-final-calibration\dryrun\20260716T164420191535Z
VALIDATOR_SELF_TEST=PASS
API_CALLS=0
........
----------------------------------------------------------------------
Ran 8 tests in 0.133s

OK
```

### Terminal calibration dry-run

Command:

```text
PYTHONDONTWRITEBYTECODE=1 python run_final_calibration.py --dry-run
```

Output:

```text
FROZEN_V1_INTEGRITY=PASS
FROZEN_V2_BASE_INTEGRITY=PASS
FROZEN_PROMPT_INTEGRITY=PASS
FROZEN_CORPUS_INTEGRITY=PASS
V3_PROMPT_SHA256=b723fbb068da8eefec9d77cfa162d2090ee680676ace3b9b5c1b2614d8c0c047
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
CORPUS_SHA256=70dff2678d974883126b480c4b2884ed2b1da059598b3f7f235972e58935b7cf
ANCHOR_COMMIT=ffb334aa6544556f989d36493de3fc5fcbb05362
CASES=40
CALLS=80
N_REPLICATES=2
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-final-calibration\dryrun\20260716T164420191535Z
VALIDATOR_SELF_TEST=PASS
API_CALLS=0
```

The dry-run created only temporary verification artifacts under `dryrun/`;
they are not part of the anchor commit. The displayed anchor is the Phase-0
commit because this verification precedes the final-calibration anchor
commit. A future real run will record the final anchor commit in its manifest.

## Pré-run audit hardening — verification 2026-07-16

The four corrections are audit-gate changes only: both replicates are shown
before one pair verdict; Rule 3 is permanently capped at five unique exclude
DOIs; offline integrity is checked before report/checklist writes; and
`response_models` is never inferred from assessment `model` fields.

### v1-calibration tests

Command:

```text
PYTHONDONTWRITEBYTECODE=1 python test_calibration.py
```

Output:

```text
.....
----------------------------------------------------------------------
Ran 5 tests in 0.064s

OK
```

### v3 checks with the temporary unlabelled fixture

The real v3 source files were not changed. The seven existing checks were
run with the same temporary empty `blocD.csv` fixture used previously:

```text
PROMPT_DIFF=PASS
FROZEN_INTEGRITY=PASS
SOURCE_DIAGNOSTIC=PASS
REPRODUCED_HARD_FAILS=PASS
FROZEN_BLOCKS=PASS
BLOCD_AND_REPLICATES=PASS
LABEL_HELPER=PASS
TESTS=7
ALL_TESTS=PASS
```

### Terminal calibration tests

Command:

```text
PYTHONDONTWRITEBYTECODE=1 python test_final_calibration.py
```

Output:

```text
FROZEN_V1_INTEGRITY=PASS
FROZEN_V2_BASE_INTEGRITY=PASS
FROZEN_PROMPT_INTEGRITY=PASS
FROZEN_CORPUS_INTEGRITY=PASS
V3_PROMPT_SHA256=b723fbb068da8eefec9d77cfa162d2090ee680676ace3b9b5c1b2614d8c0c047
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
CORPUS_SHA256=70dff2678d974883126b480c4b2884ed2b1da059598b3f7f235972e58935b7cf
ANCHOR_COMMIT=68d26fb28861a63b60f2ddf20b4a043ae747102c
CASES=40
CALLS=80
N_REPLICATES=2
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-final-calibration\dryrun\20260716T170112237635Z
VALIDATOR_SELF_TEST=PASS
API_CALLS=0
............
----------------------------------------------------------------------
Ran 12 tests in 0.732s

OK
```

### Terminal calibration dry-run

Command:

```text
PYTHONDONTWRITEBYTECODE=1 python run_final_calibration.py --dry-run
```

Output:

```text
FROZEN_V1_INTEGRITY=PASS
FROZEN_V2_BASE_INTEGRITY=PASS
FROZEN_PROMPT_INTEGRITY=PASS
FROZEN_CORPUS_INTEGRITY=PASS
V3_PROMPT_SHA256=b723fbb068da8eefec9d77cfa162d209ee680676ace3b9b5c1b2614d8c0c047
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
CORPUS_SHA256=70dff2678d974883126b480c4b2884ed2b1da059598b3f7f235972e58935b7cf
ANCHOR_COMMIT=68d26fb28861a63b60f2ddf20b4a043ae747102c
CASES=40
CALLS=80
N_REPLICATES=2
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-final-calibration\dryrun\20260716T170135748139Z
VALIDATOR_SELF_TEST=PASS
API_CALLS=0
```

No real calibration run was launched. The listed `dryrun/` directory is
temporary verification output and is removed before staging.
