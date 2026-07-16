# PREREGISTRATION — criteria-matrix v2 micro-test

This document freezes the corpus, prompt, replicate count, and success
criteria before any v2 API call. No post-observation change is permitted.

## Corpus and replicates

Every case is run with `n=2` replicates, `replicate=1` and `replicate=2`,
using the default model `deepseek-reasoner`.

- **Bloc A — non-régression**: `fp_prompt_tuning`, `fp_agent_planning`,
  `fp_ranking_evaluation`, `tp_cot_counterfactual`,
  `tp_low_resource_prompting`, `tp_when_cot_needed`,
  `state_boundary_ai_literacy`, `state_title_only_true_positive`,
  `state_title_only_prompt_tuning`.
- **Bloc B — maladie v1**: `gold_002`, `gold_003`, `gold_007`, `gold_013`,
  `gold_014`, `gold_015`, `gold_016`, `gold_019`, `gold_023`, `gold_026`,
  `gold_028`, `gold_032`, `gold_034`.
- **Bloc C — E4/I4**: `gold_031`, `gold_033`, `gold_036`, `gold_038`,
  `gold_039`, `gold_040`.
- **Bloc D — held-out frais**: `blocD_001`, `blocD_002`, `blocD_003`,
  `blocD_004`, `blocD_005`, selected deterministically from candidates.csv
  after excluding gold DOIs and empty title/abstract records. Cedric supplies
  the include/exclude labels before a real run.

Blocks B and C are reloaded verbatim from the frozen v1 calibration
`cases.jsonl`; they are not rebuilt from the review directory. Block A is
rebuilt from the imported v1 `CASE_SPECS` and the review directory. Block D
is the only held-out corpus.

## Bloc D procedure

Select records with usable `doi`, `title`, and `abstract`, whose canonical DOI
is absent from `gold_set.csv`; keep one record per canonical DOI; sort by
`sha256(doi.lower())` ascending; take the first five. Write `blocD.csv` with
columns `doi,title,abstract,label` and leave `label` empty until Cedric labels
the records. A real run refuses to start if the file is missing, malformed,
does not contain exactly five records, or contains an empty label. A dry-run
warns and runs blocks A–C only.

## Critères de réussite

- (a) Zéro erreur « requires evidence » sur l'ensemble du corpus, les deux réplicats. C'est le critère qui définit le v2 : s'il échoue, v2 falsifié.
- (b) Taux d'assessments invalides ≤ 10 % (v1 calibration : 32,5 %).
- (c) Bloc A : les critères (b), (c), (e) du PREREGISTRATION v1 tiennent encore (mêmes oracles). Toute régression = v2 falsifié.
- (d) Bloc C : E4 ∉ hard_fails sur les 5 cas refusés, dans les deux réplicats ; I4 ∉ hard_fails sur gold_031.
- (e) Zéro faux hard-fail sur tout cas labellisé include (assessment valide), blocs confondus.
- (f) Stabilité (mesure, seuil indicatif) : ensembles de hard-fails identiques entre réplicats sur ≥ 90 % des cas. Sous le seuil, v2 n'est pas falsifié mais l'exigence de reproduction avant auto-exclusion devient définitivement obligatoire dans la politique.

The criteria are evaluated per replicate unless the criterion explicitly
refers to the corpus or to the inter-replicate comparison. The allowlist
remains sealed during this micro-test. No post-observation change to the
prompt, criteria, oracle, corpus, or evaluation rules is permitted.
