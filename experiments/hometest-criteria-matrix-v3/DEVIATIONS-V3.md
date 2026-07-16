# Deviations and verification — criteria-matrix v3

## Interpretations frozen before any API call

- The Charter's original 64-call arithmetic double-counted
  `tp_cot_counterfactual`. The dated amendment controls: it is present once
  in A with `bloc_b_regression=true`; B contains the 12 gold IDs only. A–C
  therefore contain 26 unique cases / 52 calls, and the fully labelled D
  corpus contains 31 unique cases / 62 calls.
- The new D selection requires a usable title as well as a non-empty abstract,
  because the frozen D CSV contract and user message need both fields. This is
  the minimal continuation of the v2 D workflow; the registered hash filter
  and DOI exclusions are unchanged.
- A reproduced hard-fail for criteria (e)/(f) requires the hard-fail to be
  present in both replicates and both assessments to be valid. A mismatch
  diagnostic is still a validation error; v3 changes only its message.
- Stability (g) is reported per block with no falsifying threshold. The
  falsifying verdict is determined by (a)–(f), as the Charter states.
- The imported v1 `HOLDOUT_SELECTION_RULE` remains in the manifest for
  compatibility, but it is not applied to this fixed A–D corpus.
- No API call or Git command was made by the implementation or verification.
  The manifest records `git_commit` as null.

## Unified v2 → v3 prompt diff

The following is the complete diff. It contains only the source-label rule
from Charter §2.1 and the mechanical schema rename; `test_v3.py` verifies the
transform programmatically at line level.

```diff
--- v2/prompt.txt
+++ v3/prompt.txt
@@ -35,6 +35,8 @@
 - The document is supplied with a sentence index: the title is sentence T; abstract sentences are S1, S2, ...
 - For "met", "not_met", and "unclear", provide at least one evidence item. For "not_reported", evidence must be an empty array.
 - Every evidence item must be {"source": "<T or S1, S2, ...>", "quote": "<exact contiguous substring of that one sentence>"}.
+- A quote copied from the title must use source "T". "S1", "S2", ... refer
+  only to abstract sentences; never label a title quote with an "S" source.
 - Copy characters exactly as they appear in the source, including capitalization, punctuation, and formatting artifacts. Never shorten, join, smooth, or correct the text. Never use ellipses. To cite two passages, use two evidence items.
 - For exclusion criteria phrased as "X without Y": cite evidence for the X part only. The "without Y" part must be consistent with your statuses on the related inclusion criteria; do not fabricate evidence of absence.
 - "reason" must explain the relationship between the evidence and this criterion only.
@@ -44,7 +46,7 @@
 Return only one JSON object with exactly these top-level fields:
 
 {
--  "schema": "criterion_assessment.v2-microtest",
+  "schema": "criterion_assessment.v3-microtest",
   "criteria": [
     {
       "id": "criterion ID supplied below",
```

## Bloc D generation

Exact generator output from the real review directory:

```text
BLOCD_PATH=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v3\blocD.csv
BLOCD_METHOD=candidate rows with usable doi/title/abstract, DOI absent from gold_set.csv and v2 blocD.csv, unique canonical DOI, sorted by sha256(doi.lower()), first five
V2_BLOCD_EXCLUDED=10.1109/bigdata59044.2023.10386113,10.1145/3491102.3517582,10.18653/v1/2023.findings-acl.408,10.2196/50638,10.48550/arxiv.2304.11556
BLOCD_DOIS=10.1145/3545945.3569823,10.18653/v1/2023.acl-long.153,10.1109/cvpr52729.2023.01438,10.1038/s41746-025-01475-8,10.1145/3491101.3503564
BLOCD_ROWS=5
```

All five labels in this generated v3 file are empty for Cedric's pre-run
screening.

## Verification outputs

`PYTHONDONTWRITEBYTECODE=1 python test_v3.py`:

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

Real-directory dry-run with D intentionally unlabelled:

```text
FROZEN_V1_INTEGRITY=PASS
FROZEN_V2_BASE_INTEGRITY=PASS
FROZEN_PROMPT_INTEGRITY=PASS
V1_PROMPT_SHA256=eab475df17a7247e8ab9d3ee0648864849a8cf84e1d437147531d5267a633698
V2_PROMPT_SHA256=80651214c445bcdd992ecae07feffbd8dfd981ecf4b075921eadcaff417701f3
V3_PROMPT_SHA256=b723fbb068da8eefec9d77cfa162d2090ee680676ace3b9b5c1b2614d8c0c047
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
WARNING=blocD.csv has an empty label; Cedric must label all five records before a real run
BLOCK_A_CASES=9
BLOCK_B_CASES=12
BLOCK_C_CASES=5
BLOCK_D_CASES=0
CASES=26
CALLS=52
N_REPLICATES=2
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v3\dryrun\20260716T144505124237Z
VALIDATOR_SELF_TEST=PASS
```

The labelled-fixture test verifies the corresponding no-D-issues target:
31 cases and 62 replicate calls.

Exact labelled-fixture dry-run output:

```text
FROZEN_V1_INTEGRITY=PASS
FROZEN_V2_BASE_INTEGRITY=PASS
FROZEN_PROMPT_INTEGRITY=PASS
V1_PROMPT_SHA256=eab475df17a7247e8ab9d3ee0648864849a8cf84e1d437147531d5267a633698
V2_PROMPT_SHA256=80651214c445bcdd992ecae07feffbd8dfd981ecf4b075921eadcaff417701f3
V3_PROMPT_SHA256=b723fbb068da8eefec9d77cfa162d2090ee680676ace3b9b5c1b2614d8c0c047
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
BLOCK_A_CASES=9
BLOCK_B_CASES=12
BLOCK_C_CASES=5
BLOCK_D_CASES=5
CASES=31
CALLS=62
N_REPLICATES=2
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v3\dryrun\20260716T144413038132Z
VALIDATOR_SELF_TEST=PASS
```
