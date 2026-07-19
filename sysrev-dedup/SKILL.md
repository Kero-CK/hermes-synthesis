---
name: sysrev-dedup
description: >
  Déduplique les articles candidats d'une revue de littérature.
  À utiliser après search, quand candidates.csv est constitué.
  Détecte les doublons par DOI exact et par similarité de titre.
  Correspond au module M3 du pipeline Hermes Synthesis.
inputs:
  - /reviews/<id>/candidates.csv
  - /reviews/<id>/manifest.json (stage = "search_done")
outputs:
  - /reviews/<id>/candidates.csv (dédupliqué)
  - /reviews/<id>/candidates_raw.csv (backup avant dédup)
  - journal d'audit mis à jour
  - prisma.json ("after_dedup") et manifest.json mis à jour
requires:
  env: []
  tools: [terminal]
  scripts: [scripts/dedup.py]
---

# Objectif

Identifier et fusionner les doublons dans `candidates.csv` en trois passes :
identité exacte, titre normalisé identique, puis similarité de titre sous
garde-fous. Produire un fichier
dédupliqué propre et tracer toutes les fusions pour l'audit.

# Pré-conditions

- `manifest.json` indique `stage = "search_done"`
- `candidates.csv` existe avec des données

# Procédure

1. Vérifie que `candidates.csv` existe et contient des lignes.

2. Exécute :
   ```
   python3 ~/.hermes/skills/sysrev/sysrev-dedup/scripts/dedup.py '<json>'
   ```
   avec :
   ```json
   {
     "id": "adaptation-pme-2026",
     "threshold": 0.90
   }
   ```
   - `threshold` : seuil de similarité titre (0.0–1.0). Défaut : 0.90.
     Plus bas = plus agressif (fusionne des titres moins ressemblants).

3. Le script :
   - Sauvegarde `candidates.csv` en `candidates_raw.csv` (backup)
   - Passe 1 : fusionne les DOI, `source_id` ou `oa_url` identiques
   - Passe 2 : fusionne les titres normalisés identiques si les années sont
     identiques, voisines ou absentes
   - Passe 3 : fusionne les titres similaires (ratio ≥ threshold) seulement si
     les années sont compatibles et qu'au moins un DOI manque
   - Pour chaque fusion, conserve la ligne la plus complète (priorité :
     abstract présent > oa_url présent > date la plus récente)
   - Journalise chaque fusion dans `decisions.jsonl`
   - Réécrit `candidates.csv` dédupliqué
   - Met à jour `prisma.json` (`after_dedup`) et `manifest.json`

4. Lis le rapport de déduplication affiché par le script et présente
   un résumé à l'utilisateur : nombre de doublons trouvés, articles
   conservés, cas litigieux éventuels.

# Règles

- **Ne jamais supprimer sans tracer.** Chaque fusion génère une entrée
  dans `decisions.jsonl`.
- **Backup systématique.** `candidates_raw.csv` est la version pré-dédup,
  conservée pour tout audit.
- **Versions d'un même article.** La normalisation des titres ignore la casse,
  la ponctuation et les espaces multiples. Un titre identique peut donc réunir
  une version preprint et une version publiée malgré des identifiants différents,
  si leurs années sont identiques ou voisines (ou si une année manque).
- **Garde-fou fuzzy.** Une similarité approximative ne fusionne jamais deux
  DOI différents ; elle exige qu'au moins un DOI soit absent et que les années
  soient compatibles.
- **Audit générique.** Chaque fusion conserve la ligne la plus complète et
  journalise l'identité gardée, `merged_ids`, `merged_sources` et le score
  éventuel. `merged_dois` reste écrit pour compatibilité avec les anciens
  lecteurs ; les anciens journaux ne sont pas réécrits.
- **Seuil raisonnable.** 0.85 par défaut. Ne pas descendre sous 0.75 sans
  alerter l'utilisateur (risque de faux positifs).
- Si aucun doublon trouvé, c'est normal : le script le signale sans erreur.

# Pièges connus

- **O(n²) — comparaison de titres explosive sur gros corpus.** La passe fuzzy
  compare les titres à tous les autres → O(n²).
  Pour 500 lignes : ~1 min. Pour 2000 lignes : ~1 heure (paralysant).
  **Quand `candidates.csv` dépasse 1000 lignes**, évaluer avec prudence la
  passe fuzzy et la réaliser de préférence sur le corpus final screené.

  **DOI-only dedup rapide :**
  ```python
  seen = set()
  for row in csv.DictReader(f):
      doi = row.get('doi','').strip()
      if doi and doi in seen: continue
      if doi: seen.add(doi)
      rows.append(row)
  ```

- **Timeout sur `dedup.py` en foreground.** Pour les corpus >500 lignes,
  lancer `dedup.py` en `background=true` avec `notify_on_complete=true`.
  Ne pas utiliser le mode foreground avec un timeout standard (120s) —
  la comparaison de titres monopolise le CPU sans produire de sortie
  intermédiaire, ce qui fait croire au timeout que le processus est bloqué.

# Journalisation

Chaque fusion génère une ligne dans `decisions.jsonl` :
```json
{"ts":"...","doc":"10.xxx/a","identity_type":"doi",
 "stage":"dedup","decision":"merge",
 "merged_ids":["10.xxx/a","https://openalex.org/W1"],
 "merged_sources":["manual","openalex"],
 "merged_dois":["10.xxx/a"],
 "reason":"titre normalisé identique — 2 versions fusionnées (années compatibles)"}
```

Mise à jour :
- `prisma.json` : `after_dedup` = nombre de lignes après dédup
- `manifest.json` : `stage = "dedup_done"`, `dedup_threshold`, `dedup_removed`

# Critère de fin (Definition of Done)

- `candidates_raw.csv` sauvegardé (backup intact)
- `candidates.csv` dédupliqué (moins de lignes ou identique si 0 doublon)
- `prisma.json.after_dedup` correct
- `manifest.json` indique `stage = "dedup_done"`
- Les fusions sont journalisées dans `decisions.jsonl`
