# Cahier des charges — criteria-matrix v2

Statut : design gelé avant implémentation. Ce document précède le
PREREGISTRATION-V2 ; il fixe le périmètre et les critères de réussite.
Rédigé après le cycle v1 complet (micro-test, calibration, phase 2, allowlist
scellée = {I1}).

## 1. Périmètre

### Ce que le v2 change

1. **Cible primaire — discipline `not_met` / `not_reported`.**
   Manifestations mesurées en v1 : 13 erreurs « requires evidence »
   (calibration, 32,5 % d'assessments invalides), refus phase 2 I2×2 et
   I4×1 (`not_met` affirmé pour une simple absence), et l'axe d'instabilité
   inter-runs (les trois bascules de statut du DOI 2308.11432 sont toutes
   sur cette frontière).

2. **Cible secondaire — glossaire E4.** Entrée enregistrée dans
   allowlist_decision.md : « a domain application » = la contribution
   primaire de l'article applique un LLM à une tâche ou un domaine précis ;
   les surveys, les overviews multi-applications et les frameworks
   d'évaluation ou systèmes ne sont pas des domain applications.
   Preuve : Règle 3, E4 refusé 5/5 sur exactement ce pattern.

3. **Méthodologie — réplicats.** Tout run v2 (test et calibration) exécute
   n=2 réplicats par cas. Un hard-fail ne compte pour l'auto-exclusion et
   les statistiques de qualification que s'il est reproduit dans les deux
   réplicats. Motif : non-déterminisme démontré de DeepSeek à température 0.

### Ce que le v2 ne change PAS

- Le texte des critères (criteria.json) : identique au v1, octet pour octet.
- Le matcher, les règles de cohérence, le contrat de citation par phrases.
- L'allowlist scellée v1 ({I1}) : elle reste en vigueur jusqu'à une
  calibration v2 complète.
- I2 et E3 restent bannis de toute allowlist (décision phase 2 v1).

## 2. Modifications du prompt (les seules)

Base : prompt v1 verbatim, plus exactement trois insertions.

### 2.1 Dans PROTOCOL DEFINITIONS, ajouter :

```
- "A domain application" means the article's primary contribution is
  applying an LLM to one specific task or domain. Surveys, overviews of
  multiple applications, evaluation frameworks, and system or security
  frameworks are not domain applications.
```

### 2.2 Dans les tie-breakers de STATUS DEFINITIONS, remplacer les deux
puces par trois :

```
- If you cannot produce a citable span, the status is "not_reported".
  "unclear" requires at least one citable span.
- "not_met" requires a span whose content contradicts the criterion. A span
  merely related to the topic does not justify "not_met".
- When an exclusion criterion simply does not apply to the article, there
  are only two valid answers: "not_met" WITH a span that contradicts the
  criterion, or "not_reported" with an empty evidence array. "not_met" with
  an empty evidence array is always invalid.
```

### 2.3 À la fin de OUTPUT CONTRACT, ajouter :

```
Before returning, check every criterion: if its status is "met", "not_met",
or "unclear" and its evidence array is empty, change its status to
"not_reported".
```

Rien d'autre. Toute tentation d'ajouter une règle pour E1/E5 (frontière
survey-avec-techniques, cas gold_025) est explicitement hors périmètre :
un seul chantier sémantique à la fois.

## 3. Micro-test v2 pré-enregistré

### Corpus (tout en n=2 réplicats)

- **Bloc A — non-régression** : les 9 cas du micro-test v1, avec le même
  oracle (primaires + alternatives inchangés).
- **Bloc B — régression de la maladie** : les 13 cas de calibration ayant
  produit « requires evidence » (gold_002, 013, 014, 023, 028, 032 + les
  cas quote/cohérence : 003, 007, 015, 016, 019, 026, 034 — la liste exacte
  est dans le rapport de calibration ; le harness la fige par case_id).
- **Bloc C — E4** : les 5 cas refusés en Règle 3 (gold_031 n'en fait pas
  partie ; ce sont 033, 036, 038, 039, 040) + gold_031 pour I4.
- **Bloc D (optionnel, recommandé)** : 5 records frais hors gold set,
  labellisés include/exclude par Cedric AVANT le run (labels décision
  uniquement, pas d'annotation par critère). Seul vrai held-out : les blocs
  B et C ont servi à concevoir le correctif.

### Critères de réussite (par réplicat sauf mention contraire)

- (a) Zéro erreur « requires evidence » sur l'ensemble du corpus, les deux
  réplicats. C'est le critère qui définit le v2 : s'il échoue, v2 falsifié.
- (b) Taux d'assessments invalides ≤ 10 % (v1 calibration : 32,5 %).
- (c) Bloc A : les critères (b), (c), (e) du PREREGISTRATION v1 tiennent
  encore (mêmes oracles). Toute régression = v2 falsifié.
- (d) Bloc C : E4 ∉ hard_fails sur les 5 cas refusés, dans les deux
  réplicats ; I4 ∉ hard_fails sur gold_031.
- (e) Zéro faux hard-fail sur tout cas labellisé include (assessment
  valide), blocs confondus.
- (f) Stabilité (mesure, seuil indicatif) : ensembles de hard-fails
  identiques entre réplicats sur ≥ 90 % des cas. Sous le seuil, v2 n'est
  pas falsifié mais l'exigence de reproduction avant auto-exclusion devient
  définitivement obligatoire dans la politique.

### Après le micro-test

Si v2 passe : re-calibration complète sur les 40 (n=2), mêmes Règles 1–3
que la calibration v1 (support en DOI uniques, hard-fails comptés seulement
si reproduits), nouvelle phase 2 échantillonnée, nouvelle allowlist scellée.
Candidats attendus au retour : E4 (avec le glossaire), I4, E2 (support à
reconstituer), en plus de I1.

## 4. Discipline

- Prompt v2, oracle, corpus et règles commités AVANT tout appel API.
- Aucune retouche après observation. Un échec = v3, pas une réparation.
- Coût estimé : micro-test ≈ (9+13+6+5) × 2 ≈ 66 appels ; re-calibration
  ≈ 80 appels. Toujours en centimes.

Amendement pré-implémentation (2026-07-15): le schéma de sortie est renommé criterion_assessment.v2-microtest — changement mécanique sans effet sémantique.
