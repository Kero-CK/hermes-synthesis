# PREREGISTRATION — criteria-matrix v3 micro-test

This document freezes the v3 prompt, corpus, replicate count, and evaluation
rules before any v3 API call. No post-observation change is permitted.

## Corpus and replicates

Every case is run with `n=2` replicates, `replicate=1` and `replicate=2`,
using the default model `deepseek-reasoner`.

- **Bloc A — non-régression**: `fp_prompt_tuning`, `fp_agent_planning`,
  `fp_ranking_evaluation`, `tp_cot_counterfactual`,
  `tp_low_resource_prompting`, `tp_when_cot_needed`,
  `state_boundary_ai_literacy`, `state_title_only_true_positive`,
  `state_title_only_prompt_tuning`.
  `tp_cot_counterfactual` carries `bloc_b_regression=true` and is not
  duplicated in Bloc B.
- **Bloc B — régression v2**: `gold_002`, `gold_003`, `gold_007`, `gold_013`,
  `gold_015`, `gold_019`, `gold_023`, `gold_026`, `gold_028`, `gold_032`,
  `gold_034`, `gold_039`.
- **Bloc C — E4/I4**: `gold_031`, `gold_033`, `gold_036`, `gold_038`,
  `gold_040`. The E4 check also covers `gold_039` in Bloc B.
- **Bloc D — held-out frais**: `blocD_001`, `blocD_002`, `blocD_003`,
  `blocD_004`, `blocD_005`.

There are 31 unique cases and 62 calls when Bloc D is labelled and included;
until then an API-free dry-run contains A–C (26 cases, 52 calls). Blocks B and C are
reloaded verbatim from the frozen v1 calibration `cases.jsonl`; Bloc A is
rebuilt from the imported v1 `CASE_SPECS` and the review directory.

## Bloc D procedure

Select candidate rows with a usable DOI, title, and non-empty abstract, whose
canonical DOI is absent from both `gold_set.csv` and the five DOIs in the
frozen v2 `blocD.csv`; keep one row per canonical DOI; sort by
`sha256(doi.lower())` ascending; take the first five. Write `blocD.csv` with
columns `doi,title,abstract,label` and leave every `label` empty until Cedric
labels the records. A real run refuses if the file is missing, malformed, not
exactly five rows, or contains an empty label. A dry-run warns and runs A–C
only.

## Critères de réussite

- (a) Zéro erreur « requires evidence », les deux réplicats. Échec = v3 falsifié.
- (b) Zéro erreur d'étiquetage de source (le nouveau message §2.2), les deux réplicats — c'est le critère qui définit le v3. Échec = falsifié.
- (c) Taux global d'assessments invalides ≤ 10 %.
- (d) Non-régression bloc A : critères v1 (b), (c), (e) tiennent (mêmes oracles), par réplicat.
- (e) Hard-fails parasites, sémantique production : sur les cibles E4 (gold_033/036/038/039/040) et I4 (gold_031), aucun hard-fail REPRODUIT dans les deux réplicats. Échec = falsifié.
- (f) Zéro faux hard-fail reproduit sur tout cas labellisé include, blocs confondus. Échec = falsifié.
- (g) Stabilité (mesure) : % de paires de réplicats à hard-fails identiques, reporté par bloc ; pas de seuil falsifiant, la politique exige déjà la reproduction.

Criteria (a)–(g) are evaluated on the frozen assessment records. Reproduced
hard-fails require the same hard-fail ID in both valid replicates of a case;
this is the registered production interpretation for (e) and (f). No
post-observation change to the prompt, criteria, corpus, validator diagnostic,
or evaluation rules is permitted.
