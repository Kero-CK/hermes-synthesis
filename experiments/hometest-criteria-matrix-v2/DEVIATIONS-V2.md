# Deviations and verification — criteria-matrix v2

## Interpretations

- Block B and C cases are copied from the frozen v1 calibration `cases.jsonl` without rebuilding their text, sentences, or metadata; the required `bloc` field is the only added case field.
- Block A is rebuilt with the imported v1 `CASE_SPECS`, preserving its primary and alternative oracle fields and applying the v1 title-only projection behavior.
- The imported v1 `HOLDOUT_SELECTION_RULE` is recorded for manifest compatibility, but no v1 holdout selection is applied: the fixed B/C corpus and separately preregistered D procedure define the v2 corpus.
- To make “five records” deterministic and prevent duplicate candidates from consuming multiple D slots, the D proposal keeps one record per canonical DOI in addition to excluding all gold DOIs.
- With `blocD.csv` generated but still containing empty labels, the dry-run includes blocks A–C (28 cases), warns, and does not include D. A real run refuses before creating result artifacts until all five labels are supplied.
- The v1 validator is reused unchanged. The v2 schema name is translated to the imported v1 schema name only in the validation view; assessment content and all v1 validation/derivation functions remain unchanged.
- The v1 oracle criterion (c) refers to six include-labelled cases including held-out cases that are not in block A. For this v2 block-A check, the equivalent safety condition is applied to every valid include-labelled A case; criterion (e) is applied to every valid exclude-labelled A case.
- `git_commit` is recorded as null because this task performs no Git commands.

## Unified v1 → v2 prompt diff

The diff below is the complete prompt change. It contains only Charter §2.1,
§2.2, §2.3, and the mechanical schema rename; `test_v2.py` verifies the
result programmatically against `prompt.txt` from v1.

```diff
--- v1/prompt.txt
+++ v2/prompt.txt
@@ -13,6 +13,10 @@
 - "Prompt tuning", "soft prompts", "prefix tuning", "continuous prompts", and "learned prompts" denote prompt parameters trained by optimization. They are model training, not practitioner prompting, unless the abstract states the prompts are discrete, manual, natural-language instructions written by a person.
 - Naming what an LLM is used to do (plan, rank, decide, control, solve tasks) is not a prompt-engineering operation. A prompt-engineering operation must describe an operation on the prompt, context, or output: what content goes into the prompt or context; how it is constructed, structured, sequenced, selected, or transformed; or how outputs are constrained or verified.
 - [DECISION-D] Named practitioner prompting families (zero-shot prompting, few-shot / in-context examples, chain-of-thought prompting) count as identifiable, transferable prompting methods when the title or abstract states they were applied or compared.
+- "A domain application" means the article's primary contribution is
+  applying an LLM to one specific task or domain. Surveys, overviews of
+  multiple applications, evaluation frameworks, and system or security
+  frameworks are not domain applications.
 
 STATUS DEFINITIONS
 
@@ -22,8 +26,14 @@
 - "not_reported": neither the title nor the abstract contains relevant evidence with which to assess the criterion.
 
 Operational tie-breakers:
-- If you cannot produce a citable span, the status is "not_reported". "unclear" requires at least one citable span.
-- "not_met" requires a span whose content contradicts the criterion. A span merely related to the topic does not justify "not_met".
+- If you cannot produce a citable span, the status is "not_reported".
+  "unclear" requires at least one citable span.
+- "not_met" requires a span whose content contradicts the criterion. A span
+  merely related to the topic does not justify "not_met".
+- When an exclusion criterion simply does not apply to the article, there
+  are only two valid answers: "not_met" WITH a span that contradicts the
+  criterion, or "not_reported" with an empty evidence array. "not_met" with
+  an empty evidence array is always invalid.
 
 EVIDENCE CONTRACT
 
@@ -39,7 +49,7 @@
 Return only one JSON object with exactly these top-level fields:
 
 {
--  "schema": "criterion_assessment.v1-microtest",
+  "schema": "criterion_assessment.v2-microtest",
   "criteria": [
     {
       "id": "criterion ID supplied below",
@@ -52,6 +62,10 @@
   ]
 }
 
+Before returning, check every criterion: if its status is "met", "not_met",
+or "unclear" and its evidence array is empty, change its status to
+"not_reported".
+
 Return every supplied criterion exactly once, in the supplied order. Do not return a score, confidence, global decision, recommendation, hard-fail flag, or routing decision.
 
 CRITERIA
```

## Bloc D generation

The real review directory had usable `candidates.csv` and `gold_set.csv`
columns. The deterministic proposal was generated with this method:

`candidate rows with usable doi/title/abstract, DOI not in gold_set.csv,
unique canonical DOI, sorted by sha256(doi.lower()), first five`

Exact generator output:

```text
BLOCD_PATH=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v2\blocD.csv
BLOCD_METHOD=candidate rows with usable doi/title/abstract, DOI not in gold_set.csv, unique canonical DOI, sorted by sha256(doi.lower()), first five
BLOCD_DOIS=10.1145/3491102.3517582,10.2196/50638,10.48550/arxiv.2304.11556,10.1109/bigdata59044.2023.10386113,10.18653/v1/2023.findings-acl.408
BLOCD_ROWS=5
```

All five `label` cells remain empty for Cedric's pre-run labelling.

## Verification outputs

`PYTHONDONTWRITEBYTECODE=1 python test_v2.py`:

```text
PROMPT_DIFF=PASS
FROZEN_INTEGRITY=PASS
FROZEN_BLOCKS=PASS
BLOCD_REFUSAL=PASS
BLOCD_COUNTS=PASS
REPLICATES=PASS
CRITERIA_A_F=PASS
TESTS=7
ALL_TESTS=PASS
```

Real-directory dry-run:

```text
FROZEN_PROMPT_INTEGRITY=PASS
V1_PROMPT_SHA256=eab475df17a7247e8ab9d3ee0648864849a8cf84e1d437147531d5267a633698
V2_PROMPT_SHA256=4cdd8c56f937b1a7f6345ae18d117649b270fb3bee3cf6d0f487d0f07d930476
CRITERIA_SHA256=41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21
WARNING=blocD.csv has an empty label; Cedric must label all five records before a real run
BLOCK_A_CASES=9
BLOCK_B_CASES=13
BLOCK_C_CASES=6
BLOCK_D_CASES=0
CASES=28
N_REPLICATES=2
DRY_RUN_DIR=C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v2\dryrun\20260716T095851120481Z
VALIDATOR_SELF_TEST=PASS
```

The labelled-fixture test also verifies the expected 33-case total (`9+13+6+5`)
and the dry-run warning/refusal path leaves block D out at 28 cases.

## Scope and safety

All persistent files and runtime artifacts are under
`experiments/hometest-criteria-matrix-v2/`. No API call or Git command is
made by the implementation or verification commands.

## Review correction (pre-freeze, 2026-07-15)

The initial implementation re-wrapped the two existing v1 tie-breaker
bullets while inserting the third. Reviewer restored the v1 single-line
formatting in prompt.txt and aligned NEW_TIE_BREAKERS in
run_microtest_v2.py so the v1→v2 transform preserves untouched lines
byte-for-byte. The unified diff above predates this correction; the
authoritative check is test_prompt_has_exactly_four_changes, which passes
after the correction (7/7 tests, dry-run CASES=28, integrity PASS).
