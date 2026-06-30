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

Identifier et fusionner les doublons dans `candidates.csv` en deux passes :
DOI exact (certain) puis similarité de titre (fuzzy). Produire un fichier
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
     "threshold": 0.85
   }
   ```
   - `threshold` : seuil de similarité titre (0.0–1.0). Défaut : 0.85.
     Plus bas = plus agressif (fusionne des titres moins ressemblants).

3. Le script :
   - Sauvegarde `candidates.csv` en `candidates_raw.csv` (backup)
   - Passe 1 : fusionne les DOI identiques
   - Passe 2 : fusionne les titres similaires (ratio ≥ threshold)
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
- **Seuil raisonnable.** 0.85 par défaut. Ne pas descendre sous 0.75 sans
  alerter l'utilisateur (risque de faux positifs).
- Si aucun doublon trouvé, c'est normal : le script le signale sans erreur.

# Pièges connus

- **O(n²) — similarité de titres explosive sur gros corpus.** La passe 2
  (similarité de titre) compare chaque titre à tous les autres → O(n²).
  Pour 500 lignes : ~1 min. Pour 2000 lignes : ~1 heure (paralysant).
  **Quand `candidates.csv` dépasse 1000 lignes**, faire exclusivement une
  déduplication DOI (passe 1) et sauter la similarité de titres. La quasi-totalité
  des doublons inter-sources sont des DOI identiques ; les doublons de titre
  sans DOI commun sont rarissimes. Pour une comparaison broad-vs-narrow
  (étape intermédiaire), la dédup DOI-only est amplement suffisante.
  Faire la dédup titres en différé, sur le corpus final screené (beaucoup
  plus petit).

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
{"ts":"...","doc":"DOI_gardé","stage":"dedup","decision":"merge",
 "merged_dois":["10.xxx/a","10.xxx/b"],"reason":"DOI exact match"}
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
