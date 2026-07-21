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
  env: [OPENALEX_API_KEY, UNPAYWALL_EMAIL, NCBI_EMAIL]
  tools: [clarify, terminal]
  scripts: [scripts/search.py]
---

# Objectif

Interroger les bases scientifiques gratuites pour trouver des articles
correspondant à la question de recherche, réconcilier avec les PDF déposés
dans la dropzone, et produire un fichier `candidates.csv` traçable. Les
connecteurs disponibles sont OpenAlex, PubMed et ERIC.

# Pré-conditions

- `manifest.json` indique `stage = "protocol_done"`
- `protocol.md` existe avec une question et des critères
- `OPENALEX_API_KEY` est configurée ; une recherche réelle échoue explicitement
  si la clé est absente ou refusée
- `NCBI_EMAIL` est configurée pour toute recherche PubMed réelle ;
  `NCBI_API_KEY` est facultative

# Procédure

1. Lis `protocol.md` pour extraire la question de recherche et les critères.

2. **Formule la requête par source.** Pour chaque source à interroger,
   convertis la question + critères en une requête structurée utilisable
   par l'API de la source. Pour OpenAlex, le script exige un objet avec
   `query_mode = "search"` et transmet `search=` séparément de `filter=`.
   - `search` contient la recherche booléenne exacte, avec parenthèses,
     opérateurs et guillemets conservés tels quels.
   - `filter` est facultatif ; il porte séparément les bornes de date, langue
     et autres filtres structurés. Les virgules entre filtres signifient ET.
   - Exemple :
     `{"query_mode":"search","search":"(climate OR warming) AND adaptation","filter":"from_publication_date:2020-01-01"}`.
   - Toute chaîne OpenAlex, tout ancien format ou tout champ supplémentaire
     est refusé avant le réseau et aucune conversion automatique n'est faite.
   - Faire valider la syntaxe avec le guide officiel OpenAlex :
     https://developers.openalex.org/guides/searching
   - Consulter la référence officielle Works pour les champs et filtres :
     https://developers.openalex.org/api-reference/works
   - Pour PubMed, le script exige exactement :
     `{"query_mode":"pubmed","term":"(expression PubMed complète)"}`.
     `term` est transmis tel quel à ESearch ; les chaînes simples, les champs
     supplémentaires et les objets invalides sont refusés avant tout réseau et
     toute écriture.
   - PubMed utilise uniquement ESearch en POST (`usehistory=y`,
     `sort=relevance`) puis EFetch XML par lots de 200 maximum :
     https://www.ncbi.nlm.nih.gov/books/NBK25499/
   - Pour ERIC, le script exige exactement un objet avec
     `query_mode = "eric"` et un champ `search` non vide ; `sort` est
     facultatif et est transmis tel quel. L'API JSON officielle ne requiert
     pas de clé API : https://api.ies.ed.gov/eric/
   - ERIC utilise `start`/`rows` pour la pagination, avec `rows` limité à 200,
     et lit uniquement `response.numFound` comme compteur attendu. Le tri
     explicite fourni dans la requête est conservé.

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
         "openalex": {
           "query_mode": "search",
           "search": "SME climate adaptation",
           "filter": "from_publication_date:2015-01-01"
         },
         "pubmed": {
           "query_mode": "pubmed",
           "term": "(SME climate adaptation[Title/Abstract])"
         },
         "eric": {
           "query_mode": "eric",
           "search": "higher education AND generative AI",
           "sort": "publicationdateyear desc"
         }
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
- **PubMed — secrets et provenance.** `NCBI_EMAIL` et `NCBI_API_KEY` servent
  uniquement aux appels E-utilities et ne doivent apparaître ni dans
  `candidates.csv`, ni dans `manifest.json`, ni dans les logs. L'identité
  Hermes d'un article est `https://pubmed.ncbi.nlm.nih.gov/{PMID}/` ; un
  PMCID renseigne `oa_url` avec l'URL PMC canonique
  `https://pmc.ncbi.nlm.nih.gov/articles/{PMCID}/` ; le texte intégral PMC est
  ensuite récupéré via EFetch XML par sysrev-fulltext.
- **ERIC — provenance et accès.** ERIC est une source spécialisée en sciences
  de l'éducation ; son API JSON officielle ne requiert pas de clé API.
  `search` et `sort` sont conservés exactement dans la provenance, tandis que
  l'identifiant ERIC devient `https://eric.ed.gov/?id=<ERIC_ID>`.
- **Sci-Hub désactivé.** Ne pas utiliser ni proposer Sci-Hub.
- **Épinglage de version.** Noter l'endpoint et la version de chaque API
  source utilisée dans `manifest.json`.
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

- **OpenAlex — `search=` et `filter=` séparés.** Fournir un objet avec
  `query_mode = "search"` et un champ `search` non vide. Le champ `filter`
  est facultatif et conserve les filtres structurés, séparés par des virgules.
  Toute chaîne OpenAlex est refusée avant tout appel réseau et toute écriture.

- **PubMed — ESearch POST puis EFetch XML.** Fournir un objet avec
  `query_mode = "pubmed"` et un `term` non vide. Le terme est conservé
  exactement, `usehistory=y` et `sort=relevance` sont explicites, et chaque
  EFetch demande au plus 200 notices. Sans `NCBI_API_KEY`, les appels sont
  espacés pour rester à au plus 3 requêtes par seconde.

- **ERIC — JSON et pagination bornée.** Fournir un objet avec
  `query_mode = "eric"` et `search` non vide. L'endpoint officiel
  `https://api.ies.ed.gov/eric/` reçoit `format=json`, `start`, `rows` (au
  plus 200), les champs demandés et le `sort` exact éventuel. `numFound` doit
  être un entier non négatif ; s'il est absent ou invalide, le statut est
  `incomplete` avec `expected = null`. Une erreur de page conserve les notices
  déjà reçues et ne devient jamais silencieusement `complete`.

- **Tester la requête avant le script.** En cas de doute, lancer un appel
  API direct (curl ou Python one-liner) pour vérifier le compte de résultats
  et la pertinence. 400 = syntaxe invalide.

- **Plafond historique de 50 résultats (corrigé).** Le script `search.py`
  avait un `max_results=50` en dur dans `_openalex_search()` jusqu'en
  juin 2026. Toute revue antérieure peut être biaisée par ce plafond
  (marquée `plafond_biais` dans son `manifest.json`). Le script pagine
  désormais jusqu'à épuisement (per_page=100). Le garde-fou est `HARD_LIMIT`
  (variable d'env, défaut 2000) — voir ci-dessous.

- **HARD_LIMIT configurable.** Le plafond de sécurité se règle via
  `HARD_LIMIT` (défaut 2000). Pour un gros corpus, monter avant de lancer :
  `export HARD_LIMIT=5000`. Si le plafond est atteint, `search_status = "capped"`
  (≠ "incomplete" : c'est un choix, pas un échec). On peut relancer avec
  un `HARD_LIMIT` plus haut sans risque de mélange (le CSV est réécrit en
  mode `"w"`). **Note :** le curseur peut être activé dès que
  `meta.count > 10000`; un `HARD_LIMIT` inférieur arrête généralement la
  collecte avant que le curseur ne soit utile.

- **Pagination cursor au-delà de 10000 résultats.** La pagination par "page"
  plafonne à 10 000 résultats côté OpenAlex. Si `meta.count > 10000`, le
  script bascule automatiquement sur la pagination cursor (`cursor=*` puis
  `meta.next_cursor`). Décision prise UNE SEULE FOIS au premier passage
  (flag `count_checked`), jamais re-basculée. La 1ère page (mode "page")
  est jetée (`continue` avant traitement) et re-récupérée en mode cursor
  → 0 doublon. Garde-fou anti-boucle infinie : `max_cursor_pages = 500`
  (~50k résultats max avec `per_page=100`).

- **UNPAYWALL_EMAIL comme contact User-Agent.** Le script lit
  `UNPAYWALL_EMAIL` depuis l'environnement pour le header `User-Agent`
  (`mailto:`). Sans cette variable, fallback sur `hermes-synthesis@example.org`.
  Cette adresse sert uniquement de contact dans le User-Agent.
  Le connecteur de recherche n'appelle pas l'API Unpaywall ; le fallback
  Unpaywall éventuel appartient exclusivement à `sysrev-fulltext` pour un
  article déjà inclus avec DOI.

- **HTTP 429/5xx — retry avec backoff exponentiel, JAMAIS sauter une page.**
  Sur un 429 (rate limit), 500, 502, 503, ou 504 (erreur serveur temporaire),
  le script réessaie la MÊME page avec un délai exponentiel :
  1s → 2s → 4s (max 4 tentatives, sans attente après le dernier essai).
  Si les 4 tentatives échouent :
  `status = "incomplete"` et la raison inclut le code HTTP (`last_error_code`
  stocké dans le except, utilisé après la boucle — ne pas référencer `e`
  hors du bloc except). **Ne jamais** abandonner une page silencieusement
  et continuer → ça produirait un corpus partiel présenté comme complet.

- **Détection d'incomplétude — 4 statuts distincts dans le manifest.**
   `_openalex_search()`, `_pubmed_search()` et `_eric_search()` retournent
   `(results, expected_count, status, status_reason)` ; `expected_count` vaut
   `None` si le total de la source n'est pas fiable.
  avec `status` ∈ {"complete", "incomplete", "capped", "error"}. Le statut
  global dans `manifest.json` est le pire des statuts par source
  (priorité error < incomplete < capped < complete).

  | Statut | Cause | CSV écrit? | Reprise? |
  |---|---|---|---|
  | `complete` | `retrieved == expected` avec total fiable (ou zéro explicite) | oui | — |
  | `capped` | hard_limit atteint (choix) | oui | monter hard_limit |
  | `incomplete` | 429/5xx persistant, page abandonnée ou total inconnu | oui | relancer |
  | `error` | HTTP 4xx, exception réseau | oui | corriger requête |

   Une réponse OpenAlex avec `meta.count = 0`, une réponse PubMed avec
   `Count = 0` ou une réponse ERIC avec `numFound = 0`, est `complete`, avec
   `reason = "zero_results"`.

   **Le CSV est écrit après une exécution de recherche** (même en
   `error`/`incomplete`) — c'est le manifest qui porte le statut réel. Une
   requête invalide, notamment une chaîne OpenAlex ou PubMed, est refusée avant
   réseau et aucune sortie n'est écrite.
  Un corpus `incomplete` ne passera jamais pour `complete` en aval. Les skills
  downstream (screen, fulltext, extract) doivent lire `search_status` avant de
  continuer.

  **`last_error_code` — piège Python.** La variable d'exception `e` est
  effacée à la sortie du bloc `except` en Python 3. Stocker `e.code` dans
  `last_error_code` À L'INTÉRIEUR du except, avant d'en sortir. Initialiser
  `last_error_code = None` avant la boucle retry. Ne jamais référencer `e`
  hors du except.

- **Contrat et registre des connecteurs.** `SearchResult` est l'alias de
  `tuple[list[dict], int | None, SearchStatus, str]` et représente toujours
  `(results, expected_count, status, reason)`. `SearchStatus` vaut
  `complete`, `incomplete`, `capped` ou `error`. Le registre
  `CONNECTOR_REGISTRY` contient `openalex`, `pubmed` et `eric`. PubMed utilise
  `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi` comme endpoint
  déclaré, `fetch_endpoint` vaut
  `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi`,
  `api_version = "NCBI E-utilities"` et `query_mode = "pubmed"`.
  ERIC utilise `https://api.ies.ed.gov/eric/`, `api_version = "ERIC API"` et
  `query_mode = "eric"`, sans clé API obligatoire.
  `search_source(source, query)` interroge une seule source et valide ce
  contrat ; `mcp_search` reste son alias rétrocompatible. La validation
  exige une liste `results`, un `expected_count` entier supérieur ou égal à
  zéro ou `None` si le total est inconnu, un statut autorisé et une chaîne
  `reason`. Un contrat invalide est enregistré par `main()` comme une
  erreur. `mock_search` retourne
  `(results, len(results), "complete", "mock")`. La priorité globale traite
  tout statut inconnu de manière défensive comme une erreur, jamais comme
  `complete`.

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
title,doi,source_id,year,abstract,oa_url,pdf_status,source,query,date
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
    "queries": {
      "openalex": {
        "query_mode": "search",
        "search": "climate adaptation",
        "filter": "from_publication_date:2020-01-01"
      }
    },
    "search_status": "complete|incomplete|capped|error",
    "search_meta": {
       "openalex": {
         "endpoint": "https://api.openalex.org/works",
         "api_version": "unversioned",
         "query_mode": "search",
         "retrieved": 588,
         "expected": 588,
         "status": "complete",
         "reason": ""
       },
       "pubmed": {
         "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
         "fetch_endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
         "api_version": "NCBI E-utilities",
         "query_mode": "pubmed",
         "retrieved": 588,
         "expected": 588,
         "status": "complete",
         "reason": ""
       }
    },
    "updated": "2026-06-30T..."
  }
  ```

  Quand la source ne fournit pas de total fiable, `expected` vaut `null` et
  le statut doit rendre cette incertitude explicite (`incomplete`).

# Critère de fin (Definition of Done)

- `candidates.csv` existe et contient au moins 1 ligne (ou zéro documenté)
- Toutes les colonnes de provenance sont remplies
- `prisma.json.identified` est correct
- `manifest.json` indique `stage = "search_done"`
