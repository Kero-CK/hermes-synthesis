# criteria-matrix v2 micro-test report

Results directory: `results\20260716T121416997291Z`

## Overall verdict: **v2 falsified**

A failure of (a)–(e) falsifies v2. A failure of (f) does not falsify v2, but makes replicate reproduction mandatory before any auto-exclusion.

## Criteria (a)–(f)

| Criterion | Status | Numbers / reason |
|---|---|---|
| (a) | **FAIL** | 2 requires-evidence errors across 66 records. |
| (b) | **FAIL** | 19/66 invalid (28.8%); threshold ≤10%. |
| (c) | **PASS** | r1: oracle 2/3, include false 0, exclude→include 0; r2: oracle 3/3, include false 0, exclude→include 0 |
| (d) | **FAIL** | E4 violations=4; I4 violations=0; E4 records=10/10, I4 records=2/2. |
| (e) | **PASS** | 0 valid include records with hard-fails. |
| (f) | **FAIL** | 17/33 comparable pairs identical (51.5%); incomplete=0. |

## Invalid assessments by block and replicate

| Bloc | Réplicat | Records | Invalides | Taux |
|---|---:|---:|---:|---:|
| A | 1 | 9 | 1 | 11.1% |
| A | 2 | 9 | 2 | 22.2% |
| B | 1 | 13 | 6 | 46.2% |
| B | 2 | 13 | 6 | 46.2% |
| C | 1 | 6 | 1 | 16.7% |
| C | 2 | 6 | 0 | 0.0% |
| D | 1 | 5 | 2 | 40.0% |
| D | 2 | 5 | 1 | 20.0% |
| ALL | — | 66 | 19 | 28.8% |

## Error taxonomy

The registered `requires evidence` category is listed first.

| Error class | Count |
|---|---:|
| requires evidence | 2 |
| coherence | 4 |
| quote/evidence grounding | 22 |

## Block A non-regression against v1 oracles

| Replicate | Oracle hits | FP total | Oracle criterion (b) | Valid include hard-fails | Exclude routed include |
|---:|---:|---:|---|---:|---:|
| 1 | 2 | 3 | PASS | 0 | 0 |
| 2 | 3 | 3 | PASS | 0 | 0 |

## Block C E4/I4 hard-fail checks

E4 target cases: gold_033, gold_036, gold_038, gold_039, gold_040; violations: gold_036, gold_038, gold_039, gold_040.
I4 target case: gold_031; violations: none.

## Include hard-fail safety check

Valid include records with hard-fails: none.

## Inter-replicate stability

17/33 comparable case/model pairs have identical hard-fail sets (51.5%); incomplete pairs: none.

