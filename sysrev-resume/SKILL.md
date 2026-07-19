---
name: sysrev-resume
description: >
  Reprend une revue interrompue exactement là où elle s'était arrêtée.
  Lit le curseur d'état dans manifest.json et indique la prochaine
  étape à exécuter. À utiliser après avoir fermé l'ordinateur ou changé
  de session.
inputs:
  - /reviews/<id>/manifest.json (stage actuel)
outputs:
  - affiche l'état et la prochaine action à mener
requires:
  env: []
  tools: [terminal]
  scripts: []
---

# Objectif

Éviter au chercheur de devoir se souvenir où il en était. La skill lit
le `stage` dans `manifest.json` et dit : « Tu en es à l'étape X. La
prochaine action est Y. »

# Pré-conditions

- Une revue existe dans `/reviews/<id>/`
- `manifest.json` contient un champ `stage`

# Procédure

1. Demande le `slug` de la revue si non fourni.

2. Lis `manifest.json` et affiche l'état complet :
   - ID de la revue
   - Stage actuel
   - Type de revue (scoping/systematic)
   - Dernière mise à jour
   - Prochaine étape recommandée

3. Propose de lancer la prochaine skill directement.

# États et transitions

| Stage actuel | Prochaine action |
|---|---|
| `protocol_done` | Lancer `search` |
| `search_done` | Lancer `dedup` |
| `dedup_done` | Lancer `screen` |
| `screen_done` | Si `to_review.jsonl` non vide → lancer `review` / sinon → lancer `fulltext` |
| `review_done` | Lancer `fulltext` |
| `fulltext_done` | Lancer `screen-fulltext` (éligibilité sur texte intégral) |
| `screen_fulltext_done` | Si `to_review_fulltext.jsonl` non vide → lancer `review` (queue `fulltext`) / sinon → lancer `extract` |
| `review_fulltext_done` | Lancer `extract` |
| `extract_done` | Lancer `report` |
| `report_done` | Revue terminée ✅ |

# Critère de fin

L'utilisateur sait exactement quelle skill lancer ensuite.
