# PREREGISTRATION — hometest-criteria-matrix-v1

## Oracle complet

Les neuf cas de base conservent les mêmes `case_id`, DOI et variantes que le
v0. Les faux positifs connus ont l’oracle suivant :

- `fp_prompt_tuning` : primaire `E2_MODEL_TRAINING_ONLY`; alternative acceptée
  `I4_PRACTITIONER`.
- `fp_agent_planning` : primaire `I1_PROMPT_TECHNIQUE`; alternative acceptée
  `E1_NO_ACTIONABLE_TECHNIQUE`.
- `fp_ranking_evaluation` : primaire `E3_BENCHMARK_ONLY`; alternatives
  acceptées `E1_NO_ACTIONABLE_TECHNIQUE` et
  `E4_APPLICATION_WITHOUT_PROMPT_DETAIL`.
- Les trois cas `tp_*` ont `expected_primary=null` et aucune alternative.
- Les cas boundary et title-only ont `expected_primary=null` et aucune
  alternative; ils servent à la couverture et n’ont pas de critère
  d’acceptation.

## Règle de sélection held-out

Depuis `gold_set.csv` sous `--review-dir`, exclure les DOI déjà présents dans
`CASE_SPECS`, écarter les lignes dont l’abstract est vide, trier par la valeur
hexadécimale croissante de `sha256(doi.lower())`, puis prendre les trois
premières lignes `label=exclude` (`holdout_exclude_1..3`) et les trois
premières lignes `label=include` (`holdout_include_1..3`). Les six cas ont la
catégorie correspondante, la variante `title_abstract`,
`expected_primary=null` et `accepted_alternatives=[]`. La sélection est
persistée dans le manifest avant tout appel API.

## Spécification du matcher

L’ordre exact de normalisation de `normalize_span` est :

1. NFKC.
2. `casefold`.
3. Remplacer `’` et `‘` par `'`.
4. Remplacer `“` et `”` par `"`.
5. Dé-échappement LaTeX : `\%` vers `%`, `\&` vers `&`, `\_` vers `_`,
   `\#` vers `#`.
6. Remplacer `~` par une espace.
7. Réduire toute séquence d’espaces à une espace ASCII.
8. `strip`.

Une citation est valide si la forme normalisée de `quote` est une sous-chaîne
de la forme normalisée de la phrase référencée, et si sa source est `T` ou un
`Sk` existant. Une citation contenant `...` ou `…` est rejetée avec l’erreur
`quote contains ellipsis`. Les citations sont recherchées dans une seule
phrase; une sous-chaîne à cheval sur deux phrases est invalide.

La segmentation utilise exactement la regex
`(?<=[.!?])\s+(?=[A-Z<])`. La garde ne découpe pas lorsque le texte situé
immédiatement avant la frontière se termine par `i.e.`, `e.g.` ou `etc.`
(insensible à la casse). Les phrases sont persistées dans `cases.jsonl` sous
`sentences` avec leur source (`S1`, `S2`, …) et leur texte.

## Règles de cohérence inter-critères

- `E1_NO_ACTIONABLE_TECHNIQUE=met` exige
  `I1_PROMPT_TECHNIQUE ∈ {not_met, not_reported}`.
- `E3_BENCHMARK_ONLY=met` exige
  `I2_REPRODUCIBLE ∈ {not_met, not_reported}`.
- `E4_APPLICATION_WITHOUT_PROMPT_DETAIL=met` exige
  `I2_REPRODUCIBLE ∈ {not_met, not_reported}`.
- `E2_MODEL_TRAINING_ONLY=met` exige `I4_PRACTITIONER ≠ met`.
- `I4_PRACTITIONER=met` exige `I1_PROMPT_TECHNIQUE ≠ not_met`.

Ces erreurs sont enregistrées dans `coherence_errors`, séparément de
`validation_errors`. Une erreur de cohérence rend l’assessment invalide pour
le routage et l’acceptation; une erreur de validation rend le routage
`invalid_assessment`. Les règles d’acceptation ci-dessous s’appliquent
ensuite, le cas `holdout_exclude` étant accepté dès lors qu’il n’est pas routé
`include` et qu’il ne contient pas de `coherence_error`.

## Critères de réussite et d’échec

Par modèle — RÉUSSITE si : (a) ≥ 95 % des items d'évidence valides ; (b) hard-fail primaire-ou-alternatif, mécaniquement valide, sur ≥ 2/3 des FP originaux ; (c) ZÉRO faux hard-fail sur les 6 cas include-labeled (3 TP + 3 holdout_include) avec assessment valide — un seul faux hard-fail falsifie le prompt v1 ; (d) zéro coherence_error dans les assessments valides ; (e) aucun cas exclude-labeled routé include.
ÉCHEC si l'une des conditions (b), (c) ou (e) n'est pas remplie. Aucune modification du prompt, des critères, de l'oracle ou du matcher après observation des réponses. Phase 1 sans réannotation du gold set ; phase 2 limitée à la vérification humaine des hard_fails produits.
