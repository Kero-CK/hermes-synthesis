---
name: sysrev-review
description: >
  Présente tous les cas ambigus du screening au chercheur en une seule fois
  (mode batch). Le chercheur lit la liste, prend son temps, et répond avec
  ses décisions. À utiliser après screen, quand to_review.jsonl contient des
  articles que l'IA n'a pas pu classer automatiquement.
inputs:
  - /reviews/<id>/to_review.jsonl (cas ambigus)
  - /reviews/<id>/candidates.csv (pour les abstracts complets)
  - /reviews/<id>/manifest.json (stage = "screen_done")
outputs:
  - /reviews/<id>/decisions.jsonl (décisions humaines ajoutées)
  - /reviews/<id>/to_review.jsonl (mis à jour)
  - manifest.json mis à jour
requires:
  env: []
  tools: [terminal, clarify]
  scripts: [scripts/review.py]
---

# Objectif

Présenter tous les cas ambigus en une seule liste pour que le chercheur
puisse prendre son temps et décider d'un bloc, sans faire du ping-pong
avec l'IA.

# Pré-conditions

- `manifest.json` indique `stage = "screen_done"`
- `to_review.jsonl` existe avec au moins un cas

# Procédure

1. Exécute `scripts/review.py` pour formater la liste :
   ```
   python3 ~/.hermes/skills/sysrev/sysrev-review/scripts/review.py '<json>'
   ```
   avec `{"id": "ma-revue"}`.
   Le script affiche la liste formatée des cas ambigus.

2. Présente la liste complète au chercheur. **Pour les listes longues (>15 cas),
   regrouper par pertinence** pour faciliter la décision :

   ```
   🤔 26 cas à trancher.

   ### 🎯 Très probablement pertinents (score IA trompeur)
   3. Addressing the risk of maladaptation (0.30)
   4. Redefining maladaptation (0.50)

   ### ⚠️ Potentiellement pertinents
   1. Climate Change 2023 Synthesis Report (0.30)
   2. Nature-based solutions (0.30)
   ...

   ### 🔴 Probablement hors sujet
   6. Climate Change & Mental Health (0.30)
   8. Climate Endgame (0.30)
   ...
   ```

   Ce regroupement accélère la décision : le chercheur peut faire un
   "include all sauf groupe 3" plutôt que 26 décisions individuelles.

3. Explique clairement le format de réponse attendu :
   ```
   Réponds avec la liste de tes décisions :

   1. include
   2. exclude
   3. include
   ...
   ```
   **Raccourcis acceptés :** le chercheur peut donner des décisions groupées
   ("inclue tous sauf ceux du groupe 3", "exclue 6,8,10,12"). Dans ce cas,
   interpréter et appliquer sur tous les cas.

4. Le chercheur répond avec sa liste. Applique chaque décision :
   - Pour `include` → journalise `{"decision": "include", "actor": "human"}`
   - Pour `exclude` → journalise `{"decision": "exclude", "actor": "human"}`

5. Mets à jour `to_review.jsonl` (retire les cas traités) et `manifest.json`.

# Règles

- **Tous les cas d'un coup.** Ne pas faire un cas à la fois.
- **Le chercheur peut prendre son temps.** Pas de timeout, pas de pression.
- **Format de réponse flexible.** Accepter "1. include", "1-include", "include"
  tant que l'ordre correspond.

# Journalisation

Chaque décision humaine → `decisions.jsonl` avec `"actor": "human"`.

# Pièges connus

- **Le script `review.py` ne fait QUE formater.** Il affiche la liste mais
  n'applique PAS les décisions. Après que le chercheur a répondu, l'agent
  doit appliquer les décisions manuellement :
  - Journaliser chaque décision dans `decisions.jsonl` avec `"actor": "human"`
  - Vider `to_review.jsonl`
  - Mettre à jour `manifest.json` (stage → `review_done`, compteurs)
  Voir `references/apply_decisions.py` pour le snippet réutilisable.
- **Stage filter côté fulltext.** Si la review humaine est faite AVANT le
  fulltext, s'assurer que `fulltext.py` accepte aussi les décisions du stage
  `human_review` (voir pitfall dans `sysrev-fulltext`).

- **DOIs fantômes après reconstruction de `to_review.jsonl`.** Quand
  `to_review.jsonl` est vidé par une première application buggée puis
  reconstruit depuis `decisions.jsonl`, le champ `doc` (DOI) peut être
  vide si les décisions humaines erronées ont déjà écrasé les entrées
  originales. **Toujours récupérer les DOIs depuis les entrées de
  SCREENING** (`stage == "screen_title_abstract"`) et non depuis les
  entrées humaines ou le `to_review.jsonl` reconstruit. Corréler par
  ordre (les `needs_manual` du screening sont dans le même ordre que
  l'affichage de `review.py`).

- **Rollback après une première application erronée.** Si `to_review.jsonl`
  a été vidé par une première passe buggée (mauvais comptage, décision
  inversée), le reconstruire depuis `decisions.jsonl` :
  ```python
  needs = [e for e in screening_entries if e.get('decision') == 'needs_manual']
  ```
  Filtrer sur `stage == "screen_title_abstract"` pour ne garder que les
  entrées du screening original (pas les décisions humaines déjà écrites).
  Réécrire `to_review.jsonl` avec ces entrées ET nettoyer `decisions.jsonl`
  des décisions humaines erronées avant de relancer.

# Critère de fin

- Toutes les décisions sont journalisées
- `to_review.jsonl` est vidé
- `manifest.json` indique `stage = "review_done"`
- **Tous les DOIs des décisions humaines sont non-vides.** Après application,
  vérifier avec `sum(1 for e in decisions if not e.get('doc')) == 0`.
  Un DOI vide empêche `fulltext.py` de trouver l'article (pas d'OA URL
  ni de dropzone à associer) → article perdu silencieusement.
  Si des DOIs sont vides, rollback + reconstruction.
