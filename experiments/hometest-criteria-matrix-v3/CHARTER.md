# Cahier des charges — criteria-matrix v3

Statut : design gelé avant implémentation. Rédigé après la falsification du
v2 (run 20260716T121416997291Z ; diagnostic dans son REVIEW-ANALYSIS.md).

## 1. Périmètre

### Ce que le v3 change

1. **Cible primaire — l'étiquetage de source.** Mode dominant du v2
   (22 erreurs de quote) : le modèle cite le titre verbatim mais déclare
   `S1` au lieu de `T`. Correctif : une règle explicite dans le contrat
   d'évidence (§2.1) et un message de validation distinct (§2.2) qui
   sépare « quote introuvable partout » de « quote trouvée dans une autre
   source que celle déclarée » (les deux restent invalides ; seul le
   diagnostic change).

2. **Alignement test/production.** Les vérifications de hard-fails
   parasites (type critère (d) du v2) sont désormais jugées sur les
   hard-fails REPRODUITS dans les deux réplicats — la seule chose que la
   politique de production utilise. Preuve v2 : zéro violation E4
   reproduite, alors que le critère strict par réplicat échouait.

3. **Rien d'autre.** Les acquis v2 (glossaire E4, règle not_met/
   not_reported, self-check final) sont conservés tels quels : ils ont
   réduit la maladie primaire de ~85 % et ne sont pas le problème
   résiduel. n reste à 2 réplicats : les tests doivent refléter la
   sémantique de production (2/2), pas l'embellir.

### Ce que le v3 ne change PAS

Critères (criteria.json), matcher (hors nouveau message §2.2), règles de
cohérence, allowlist v1 en vigueur ({I1} + reproduction obligatoire),
I2/E3 bannis, frontière E1/E5 (gold_025) toujours hors périmètre.

## 2. Modifications

### 2.1 Prompt v3 = prompt v2 verbatim + une insertion dans EVIDENCE
CONTRACT (après la puce « Every evidence item must be… ») :

```
- A quote copied from the title must use source "T". "S1", "S2", ... refer
  only to abstract sentences; never label a title quote with an "S" source.
```

Plus le renommage mécanique du schéma en criterion_assessment.v3-microtest.
Diff v2→v3 vérifié programmatiquement : exactement ces deux changements.

### 2.2 Validateur : quand normalize(quote) est introuvable dans la source
déclarée mais présent dans une autre source du cas, l'erreur devient
« quote found in <autre source>, declared <source> » au lieu de « not found ».
Toujours une validation_error ; aucune tolérance nouvelle.

## 3. Micro-test v3 pré-enregistré (n=2 réplicats)

### Corpus

- **Bloc A — non-régression** : les 9 cas v1, oracles inchangés.
- **Bloc B — régression v2** : les cas ayant produit des erreurs au run
  v2 : tp_cot_counterfactual, gold_002, gold_003, gold_007, gold_013,
  gold_015, gold_019, gold_023, gold_026, gold_028, gold_032, gold_034,
  gold_039 (rechargés depuis les cases.jsonl gelés v2/calibration).
- **Bloc C — E4/I4** : gold_031, gold_033, gold_036, gold_038, gold_040
  (gold_039 déjà en B ; les vérifications E4/I4 s'appliquent aussi à lui).
- **Bloc D — held-out frais** : 5 nouveaux records hors gold set et hors
  bloc D v2, sélection déterministe (hash suivant), labellisés par Cedric
  avant le run via label_blocD.py.

### Critères de réussite

- (a) Zéro erreur « requires evidence », les deux réplicats. Échec = v3
  falsifié.
- (b) Zéro erreur d'étiquetage de source (le nouveau message §2.2), les
  deux réplicats — c'est le critère qui définit le v3. Échec = falsifié.
- (c) Taux global d'assessments invalides ≤ 10 %.
- (d) Non-régression bloc A : critères v1 (b), (c), (e) tiennent (mêmes
  oracles), par réplicat.
- (e) Hard-fails parasites, sémantique production : sur les cibles E4
  (gold_033/036/038/039/040) et I4 (gold_031), aucun hard-fail REPRODUIT
  dans les deux réplicats. Échec = falsifié.
- (f) Zéro faux hard-fail reproduit sur tout cas labellisé include, blocs
  confondus. Échec = falsifié.
- (g) Stabilité (mesure) : % de paires de réplicats à hard-fails
  identiques, reporté par bloc ; pas de seuil falsifiant, la politique
  exige déjà la reproduction.

### Après le micro-test

Si v3 passe : re-calibration 40 records × 2 réplicats, Règles 1–3 de la
calibration v1 avec support en DOI uniques ET hard-fails comptés
uniquement si reproduits ; nouvelle phase 2 échantillonnée ; nouvelle
allowlist scellée. Candidats attendus : E4, I4, E2, en plus de I1.

## 4. Discipline

Commit d'ancrage avant tout appel ; aucune retouche après observation ;
un échec = v4. Coût : (9+13+5+5) × 2 = 64 appels, puis ~80 pour la
re-calibration.

Amendements pré-implémentation (2026-07-16) :

(i) Le schéma de sortie est renommé criterion_assessment.v3-microtest —
changement mécanique sans effet sémantique.

(ii) tp_cot_counterfactual appartient au Bloc A et est uniquement marqué
bloc_b_regression=true, sans duplication : le corpus contient 31 cas uniques
et 62 appels (les 64 du Charter comptaient deux fois ce cas).
