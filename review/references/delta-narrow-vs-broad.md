# Protocole de comparaison Narrow vs Broad

## Objectif

Isoler l'effet du **vocabulaire de la maladaptation** sur les résultats d'une
revue en exécutant deux runs identiques qui ne diffèrent que par le bloc 1
de la requête OpenAlex. Tout le reste — critères, codebook, seuils, décisions
HITL — est maintenu constant pour que le delta soit interprétable.

## Design

| Paramètre | Broad | Narrow |
|---|---|---|
| Bloc 1 (maladaptation) | 13 termes (labels fantômes) | 2 termes canoniques |
| Blocs 2, 3, 4 | Identiques | Identiques |
| Critères inclusion/exclusion | Identiques | Identiques |
| Codebook (9 variables) | Identique | Identique |
| Seuils screening | 0.75 / 0.25 | 0.75 / 0.25 |

## Bloc 1 — Broad (13 termes)

```
(maladaptation OR maladaptive OR "adaptation failure" OR "failed adaptation"
 OR "unsuccessful adaptation" OR "maladaptive outcomes" OR "increased vulnerability"
 OR "shifting vulnerability" OR "unintended consequences" OR "adverse outcomes"
 OR "maladaptive coping" OR "erosion of adaptive capacity" OR "adaptation lock-in")
```

## Bloc 1 — Narrow (2 termes)

```
(maladaptation OR maladaptive)
```

## Règle d'or

> Si tu modifies un critère, le codebook ou une autre partie de la requête,
> tu ne sauras plus si l'écart vient du vocabulaire ou d'autre chose.

Le delta entre les deux runs est **exclusivement** attribuable à l'élargissement
du vocabulaire de la maladaptation. Tout autre changement invalide la comparaison.

## What to compare

| Métrique | Broad | Narrow | Delta |
|---|---|---|---|
| Candidats identifiés | | | |
| Inclus après screening | | | |
| Cas ambigus (HITL) | | | |
| Articles fulltext | | | |
| Cellules extraites | | | |
| Articles avec `terme_employe ≠ "maladaptation"` | | | |
| Articles sans `definition_utilisee` | | | |

## Slug convention

- `maladapt-ssf-broad` — run avec vocabulaire élargi
- `maladapt-ssf-narrow` — run avec vocabulaire canonique
