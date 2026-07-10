---
name: sysrev-search
description: >
  Récupère les articles candidats pour une revue de littérature.
  À utiliser après protocol, quand il faut interroger les bases
  scientifiques et constituer candidates.csv. Correspond au module
  M2 du pipeline Hermes Synthesis.
inputs:
  - /reviews/<id>/protocol.md (question + critères)
  - /reviews/<id>/manifest.json (stage = "protocol_done")
outputs:
  - /reviews/<id>/candidates.csv (avec provenance : source, requête, date)
  - mise à jour de prisma.json ("identified") et manifest.json
requires:
  env: [OPENALEX_API_KEY, UNPAYWALL_EMAIL]
  tools: [clarify, terminal]
  scripts: [scripts/search.py]
---

# Objectif

Interroger les bases scientifiques gratuites pour trouver des articles
correspondant à la question de recherche, réconcilier avec les PDF déposés
dans la dropzone, et produire un fichier `candidates.csv` traçable.

# Pré-conditions

- `manifest.json` indique `stage = "protocol_done"`
- `protocol.md` existe avec une question et des critères
- `OPENALEX_API_KEY` est configurée ; une recherche réelle échoue explicitement
  si la clé est absente ou refusée

# Procédure

1. Lis `protocol.md` pour extraire la question de recherche et les critères.

2. **Formule la requête par source.** Pour chaque source à interroger,
   convertis la question + critères en une requête structurée utilisable
   par l'API de la source. Pour OpenAlex, le script transmet la valeur au
   paramètre API `filter=` : il faut donc utiliser la syntaxe structurée des
   filtres, et non une chaîne booléenne libre.
   - Virgules entre filtres = ET logique.
   - Utiliser les champs `.search`, par exemple `title.search:` ou
     `title_and_abstract.search:`.
   - Ajouter les bornes avec des filtres dédiés, par exemple
     `from_publication_date:2020-01-01`.
   - Exemple : `title_and_abstract.search:climate adaptation,from_publication_date:2020-01-01`.
   - Faire valider la syntaxe avec la documentation OpenAlex :
     https://docs.openalex.org/api-entities/works/filter-works

3. **Fais valider les requêtes par l'utilisateur via `clarify`.** Montre
   chaque requête formatée et demande confirmation. Tant que l'utilisateur
   n'a pas validé, **ne lance rien**.

   **Raccourci :** si l'utilisateur fournit les requêtes formatées
   directement (ex. `openalex "IA PME productivité" crossref "AI SME"`),
   passer directement à l'étape 4.

4. Une fois validé, exécute :
   ```
   python3 ~/.hermes/skills/sysrev/sysrev-search/scripts/search.py '<json>'
   ```
   avec un JSON structuré comme suit :
   ```json
   {
     "id": "adaptation-pme-2026",
     "queries": {
       "openalex": "title_and_abstract.search:SME climate adaptation,from_publication_date:2015-01-01",
       "crossref": "SME climate adaptation France"
     }
   }
   ```

   Le script :
   - interroge chaque source listée
   - fusionne les résultats
   - réconcilie avec `/reviews/<id>/inputs/pdfs/` par DOI
   - écrit `candidates.csv` avec les colonnes de provenance

5. Vérifie le nombre de candidats trouvés. Si 0 candidat, remonte l'alerte
   à l'utilisateur : la requête est peut-être trop restrictive.

6. Mets à jour `prisma.json` (`"identified"` = nombre de lignes dans
   `candidates.csv`) et `manifest.json` (`stage = "search_done"`).

# Règles

- **Provenance obligatoire.** Chaque ligne de `candidates.csv` doit avoir
  les colonnes `source`, `query`, `date` remplies.
- **Pas de reformulation automatique.** Une fois les requêtes validées par
  l'humain, ne les change pas. Si une source ne retourne rien, le signaler
  sans inventer.
- **Sci-Hub désactivé.** Ne pas utiliser ni proposer Sci-Hub.
- **Épinglage de version.** Noter la version de paper-search-mcp utilisée
  dans `manifest.json`.
- **Symlink vault.** `/reviews` est un symlink vers le vault Obsidian.
  Les fichiers sont automatiquement dans le vault, pas besoin de copie.

- **⚠️ Le symlink `/reviews` se perd entre sessions.** L'environnement
  WSL/Docker peut effacer le symlink au redémarrage. Avant toute opération
  de search, vérifier que `/reviews` existe et pointe vers le vault :
  ```bash
  ls /reviews/maladapt-ssf-broad-full-v2/candidates.csv || \
  ln -s "/vault/Projets/Hermes Synthesis/Reviews" /reviews
  ```
  Si `/reviews` est un dossier ordinaire (pas un symlink), les fichiers
  sont inaccessibles depuis Obsidian. Supprimer le dossier et recréer le
  symlink, puis déplacer les revues existantes dedans.

# Pièges connus

- **OpenAlex — `filter=`, pas une requête booléenne libre.** Une chaîne telle
  que `(A OR B) AND C` n'est pas le contrat consommé par `search.py`. Fournir
  au moins un champ structuré contenant `:`, puis séparer les filtres par des
  virgules. Le script rejette le texte libre avant tout appel réseau.

- **Tester la requête avant le script.** En cas de doute, lancer un appel
  API direct (curl ou Python one-liner) pour vérifier le compte de résultats
  et la pertinence. 400 = syntaxe invalide.

- **Plafond historique de 50 résultats (corrigé).** Le script `search.py`
  avait un `max_results=50` en dur dans `_openalex_search()` jusqu'en
  juin 2026. Toute revue antérieure peut être biaisée par ce plafond
  (marquée `plafond_biais` dans son `manifest.json`). Le script pagine
  désormais jusqu'à épuisement (per_page=200). Le garde-fou est `HARD_LIMIT`
  (variable d'env, défaut 2000) — voir ci-dessous.

- **HARD_LIMIT configurable.** Le plafond de sécurité se règle via
  `HARD_LIMIT` (défaut 2000). Pour un gros corpus, monter avant de lancer :
  `export HARD_LIMIT=5000`. Si le plafond est atteint, `search_status = "capped"`
  (≠ "incomplete" : c'est un choix, pas un échec). On peut relancer avec
  un `HARD_LIMIT` plus haut sans risque de mélange (le CSV est réécrit en
  mode `"w"`). **Note :** pagination cursor (filet de sécurité >10000)
  inactive tant que `HARD_LIMIT < 10000`.

- **Pagination cursor au-delà de 10000 résultats.** La pagination par "page"
  plafonne à 10 000 résultats côté OpenAlex. Si `meta.count > 10000`, le
  script bascule automatiquement sur la pagination cursor (`cursor=*` puis
  `meta.next_cursor`). Décision prise UNE SEULE FOIS au premier passage
  (flag `count_checked`), jamais re-basculée. La 1ère page (mode "page")
  est jetée (`continue` avant traitement) et re-récupérée en mode cursor
  → 0 doublon. Garde-fou anti-boucle infinie : `max_cursor_pages = 500`
  (~100k résultats max).

- **UNPAYWALL_EMAIL pour le pool courtois OpenAlex.** Le script lit
  `UNPAYWALL_EMAIL` depuis l'environnement pour le header `User-Agent`
  (`mailto:`). Sans cette variable, fallback sur `hermes-synthesis@example.org`
  — le pool courtois standard est moins prioritaire. Configurer
  `UNPAYWALL_EMAIL` améliore le rate-limit (10 req/s → ~30 req/s).

- **HTTP 429/5xx — retry avec backoff exponentiel, JAMAIS sauter une page.**
  Sur un 429 (rate limit), 502, 503, ou 504 (erreur serveur temporaire),
  le script réessaie la MÊME page avec un délai exponentiel :
  1s → 2s → 4s → 8s (max 4 tentatives). Si les 4 tentatives échouent :
  `status = "incomplete"` et la raison inclut le code HTTP (`last_error_code`
  stocké dans le except, utilisé après la boucle — ne pas référencer `e`
  hors du bloc except). **Ne jamais** abandonner une page silencieusement
  et continuer → ça produirait un corpus partiel présenté comme complet.

- **Détection d'incomplétude — 4 statuts distincts dans le manifest.**
  `_openalex_search()` retourne `(results, expected_count, status, status_reason)`
  avec `status` ∈ {"complete", "incomplete", "capped", "error"}. Le statut
  global dans `manifest.json` est le pire des statuts par source
  (priorité error < incomplete < capped < complete).

  | Statut | Cause | CSV écrit? | Reprise? |
  |---|---|---|---|
  | `complete` | `retrieved == expected` | oui | — |
  | `capped` | hard_limit atteint (choix) | oui | monter hard_limit |
  | `incomplete` | 429/5xx persistant, page abandonnée | oui | relancer |
  | `error` | HTTP 4xx, exception réseau | oui | corriger requête |

  **Le CSV est TOUJOURS écrit** (même en error/incomplete) — c'est le
  manifest qui porte le statut réel. Un corpus `incomplete` ne passera
  jamais pour `complete` en aval. Les skills downstream (screen, fulltext,
  extract) doivent lire `search_status` avant de continuer.

  **`last_error_code` — piège Python.** La variable d'exception `e` est
  effacée à la sortie du bloc `except` en Python 3. Stocker `e.code` dans
  `last_error_code` À L'INTÉRIEUR du except, avant d'en sortir. Initialiser
  `last_error_code = None` avant la boucle retry. Ne jamais référencer `e`
  hors du except.

- **Signature des fonctions de search.** Les trois fonctions
  (`_openalex_search`, `mcp_search`, `mock_search`) retournent
  `tuple[list[dict], int, str, str]` = `(results, expected_count, status, reason)`.
  `main()` déballe ce tuple. Si tu ajoutes une nouvelle source (crossref,
  pubmed), sa fonction DOIT respecter cette signature. `mock_search`
  retourne `(results, len(results), "complete", "mock")`.

- **Comparaison broad ↔ narrow : comparer les ENSEMBLES de DOI, pas les
  comptes agrégés.** Si les deux recherches plafonnent au même niveau
  (ex. 50), le delta réel est invisible. La mesure correcte est :
  `set(DOIs broad) - set(DOIs narrow)`, pas `len(broad) - len(narrow)`.
  Vérifier aussi que `narrow ⊆ broad` (sinon bug).

- **Shell escaping du JSON.** Les caractères `&`, `$`, `!`, `\"` dans les
  valeurs du JSON cassent l'appel shell direct (`python3 search.py '<json>'`).
  Le shell interprète `&` comme background, `$` comme expansion. Même le
  heredoc `cat > file << 'EOF'` peut doubler les backslash-escapes (`\\\"`).
  **Ne pas utiliser `--stdin`** — il lit du vide dans cet environnement.
  **Workaround fiable :** écrire le JSON avec `python3 -c` (échappement
  correct) puis lancer le script via `subprocess.run()` en Python :

  ```python
  python3 -c "
  import json, subprocess
  data = {'id': 'ma-revue', 'queries': {'openalex': '...'}}
  json_str = json.dumps(data, ensure_ascii=False)
  result = subprocess.run(
      ['python3', '/home/agent/.hermes/skills/sysrev/sysrev-search/scripts/search.py', json_str],
      capture_output=True, text=True, timeout=300
  )
  print(result.stdout)
  "
  ```

  Cette approche contourne complètement le shell et fonctionne à tous les coups.

# Fichiers produits

`candidates.csv` — colonnes attendues :
```
title,doi,year,abstract,oa_url,pdf_status,source,query,date
```

- `pdf_status` : `oa` (open access dispo), `dropzone` (PDF fourni par l'utilisateur), `none`
- `source` : nom de la base interrogée (ex. `openalex`, `crossref`)
- `query` : la requête exacte utilisée
- `date` : date de la recherche (ISO 8601)

# Journalisation

- `prisma.json` : `"identified"` mis à jour
- `manifest.json` :
  ```json
  {
    "stage": "search_done",
    "queries": {"openalex": "..."},
    "search_status": "complete|incomplete|capped|error",
    "search_meta": {
      "openalex": {
        "retrieved": 588,
        "expected": 588,
        "status": "complete",
        "reason": ""
      }
    },
    "updated": "2026-06-30T..."
  }
  ```

# Critère de fin (Definition of Done)

- `candidates.csv` existe et contient au moins 1 ligne (ou zéro documenté)
- Toutes les colonnes de provenance sont remplies
- `prisma.json.identified` est correct
- `manifest.json` indique `stage = "search_done"`
