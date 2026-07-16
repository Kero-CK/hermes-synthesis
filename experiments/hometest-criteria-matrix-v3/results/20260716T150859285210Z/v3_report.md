# criteria-matrix v3 micro-test report

VERDICT=v3 falsified

Results directory: `C:\Users\cedri\hermes-docker\data\skills\sysrev\experiments\hometest-criteria-matrix-v3\results\20260716T150859285210Z`

## Critères (a)–(g)

| Criterion | Status | Numbers / reason |
|---|---|---|
| (a) | **PASS** | 0 requires-evidence errors / 62 records. |
| (b) | **FAIL** | 3 source-label mismatch errors / 62 records. |
| (c) | **FAIL** | 14/62 invalid (22.6%); threshold ≤10%. |
| (d) | **FAIL** | r1: oracle 1/3, include false 0, exclude→include 0; r2: oracle 2/3, include false 0, exclude→include 0 |
| (e) | **FAIL** | E4 reproduced violations=1; I4 reproduced violations=0. |
| (f) | **FAIL** | 1 reproduced include hard-fail cases. |
| (g) | **PASS** | A: 4/9 identical (44.4%); B: 5/12 identical (41.7%); C: 1/5 identical (20.0%); D: 4/5 identical (80.0%) |

## Invalid assessments by block and replicate

| Bloc | Réplicat | Records | Invalides | Taux |
|---|---:|---:|---:|---:|
| A | 1 | 9 | 1 | 11.1% |
| A | 2 | 9 | 3 | 33.3% |
| B | 1 | 12 | 3 | 25.0% |
| B | 2 | 12 | 3 | 25.0% |
| C | 1 | 5 | 0 | 0.0% |
| C | 2 | 5 | 1 | 20.0% |
| D | 1 | 5 | 2 | 40.0% |
| D | 2 | 5 | 1 | 20.0% |
| ALL | — | 62 | 14 | 22.6% |

## Error taxonomy

The registered source-label mismatch class is listed first.

| Error class | Count |
|---|---:|
| source-label mismatch | 3 |
| coherence | 7 |
| quote/evidence grounding | 24 |

## Block A non-regression against v1 oracles

| Replicate | Oracle hits | FP total | Oracle pass | Valid include hard-fails | Exclude routed include |
|---:|---:|---:|---|---:|---:|
| 1 | 1 | 3 | FAIL | 0 | 0 |
| 2 | 2 | 3 | PASS | 0 | 0 |

## Reproduced hard-fail parasite checks

E4 targets: gold_033, gold_036, gold_038, gold_039, gold_040; reproduced violations: deepseek-reasoner/gold_040.
I4 targets: gold_031; reproduced violations: none.

## Reproduced include safety

Reproduced hard-fails on valid include cases: deepseek-reasoner/blocD_005.

## Stability by block

- Bloc A: 4/9 pairs identical (44.4%); incomplete=0.
- Bloc B: 5/12 pairs identical (41.7%); incomplete=0.
- Bloc C: 1/5 pairs identical (20.0%); incomplete=0.
- Bloc D: 4/5 pairs identical (80.0%); incomplete=0.
