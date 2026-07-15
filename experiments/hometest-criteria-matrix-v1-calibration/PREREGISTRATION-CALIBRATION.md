# PREREGISTRATION-CALIBRATION

Objectif : fonder la allowlist `auto_excludable` du modèle deepseek-reasoner sous le prompt v1 gelé. Ce run ne teste pas le prompt (déjà validé) ; il mesure.

Critères candidats : E1_NO_ACTIONABLE_TECHNIQUE, E2_MODEL_TRAINING_ONLY, E4_APPLICATION_WITHOUT_PROMPT_DETAIL, E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE, I1_PROMPT_TECHNIQUE, I4_PRACTITIONER. I2_REPRODUCIBLE et E3_BENCHMARK_ONLY sont exclus d'office (phase 2 du micro-test : 0/2 et 1/2 confirmés). L'auto-exclusion depuis un titre seul reste interdite indépendamment de la allowlist.

Règle 1 (disqualification mécanique) : un critère candidat X est disqualifié si X apparaît dans les hard_fails d'AU MOINS UN record labellisé include avec assessment valide (zéro validation_error, zéro coherence_error).

Règle 2 (support minimal) : X doit être un hard-fail sur au moins 3 DOI uniques labellisés exclude avec assessment valide, en cumulant micro-test v1 et calibration (un même DOI présent dans les deux corpus ou sous plusieurs variantes ne compte qu'une fois).

Règle 3 (vérification humaine échantillonnée) : pour chaque X encore qualifié, échantillon d'au plus 5 instances de hard-fail sur des records exclude avec assessment valide, hors les 7 DOI du micro-test (déjà vérifiés en phase 2) ; sélection déterministe par tri croissant de sha256(doi_minuscule + ":" + criterion_id). Exigence : 100 % de CONFIRMÉ sur l'échantillon — un seul REFUSÉ retire X de la allowlist jusqu'au v2.

Signal d'alerte (reporté, non disqualifiant) : hard-fails de X sur des records include au sein d'assessments INVALIDES — comptés et listés dans le rapport.

Aucune modification du prompt, des critères, du matcher ou de ces règles après observation des réponses.

## Amendements pré-run

2026-07-15 — Règle 2 resserrée d'un comptage d'occurrences à un comptage de DOI uniques, avant tout appel API de calibration.
