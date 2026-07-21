---
name: sysrev-fulltext
description: >
  Récupère et parse les textes intégraux des articles inclus après screening.
  Récupère les articles PMC par EFetch XML, télécharge les PDF non-PMC et
  parse les PDF dropzone, puis convertit le tout en Markdown exploitable.
  Correspond au module M5 du pipeline Hermes Synthesis.
inputs:
  - /reviews/<id>/decisions.jsonl (décisions de screening finales)
  - /reviews/<id>/candidates.csv (pour les URLs OA et chemins dropzone)
  - /reviews/<id>/inputs/pdfs/ (dropzone)
  - /reviews/<id>/manifest.json (stage = "screen_done" ou "review_done")
outputs:
  - /reviews/<id>/sources/<doi_safe>.md (un fichier par article inclus)
  - prisma.json ("fulltext_assessed", "fulltext_retrieved",
    "fulltext_not_retrieved") mis à jour
  - manifest.json mis à jour
requires:
  env: []
  tools: [terminal]
  scripts: [scripts/fulltext.py]
---

# Objectif

Récupérer le texte intégral de chaque article inclus lors du screening.
Pour les notices PMC, utiliser EFetch XML officiel et convertir le JATS en
Markdown. Pour les autres articles, utiliser l'URL open access puis la
dropzone (PDF fournis par l'utilisateur). Convertir en Markdown pour les
étapes suivantes (extraction notamment).

# Pré-conditions

- `manifest.json` indique `stage = "screen_done"` ou `"review_done"`
- `decisions.jsonl` contient des décisions de screening automatiques ou humaines
- `candidates.csv` contient les URLs OA et les chemins dropzone

# Procédure

1. Identifie les articles à traiter depuis les stages de screening. Une décision
   humaine prime toujours sur une décision automatique ; à priorité égale, la
   dernière décision gagne.

2. Exécute le script :
   ```
   python3 ~/.hermes/skills/sysrev/sysrev-fulltext/scripts/fulltext.py '<json>'
   ```
   avec :
   ```json
   {
     "id": "ma-revue",
     "mock": true
   }
   ```

3. Le script, pour chaque article inclus :
   - Réutilise d'abord un Markdown existant et valide
   - Regroupe les PMCID des URL PMC canoniques ou historiques (`.../articles/PMC.../pdf/`) et les récupère en un ou plusieurs appels EFetch PMC POST
   - Convertit les vrais corps JATS PMC en Markdown, en conservant titre,
     résumé, titres de sections et paragraphes ; un texte de 500 caractères
     ou moins est refusé
   - Pour une URL OA non-PMC, télécharge puis parse le PDF via
     `pymupdf4llm` en mode réel ; après échec, essaie la dropzone
   - Pour un PMCID sans corps exploitable, essaie ensuite la dropzone ; il ne
     faut jamais télécharger directement `.../articles/PMC.../pdf/`
   - Écrit le résultat dans `sources/<doi_safe>.md`
   - Si le parsing échoue, marque `retrieval_failed`

4. Présente le résumé : combien récupérés, combien en échec.

# Règles

- **Ne jamais inventer de contenu.** Si le PDF est inaccessible, passer
  en `retrieval_failed` plutôt que de générer un faux texte.
- **PMC officiel.** Les URL PMC canoniques et anciennes URL `/pdf/` servent
  uniquement à extraire le PMCID ; le texte est obtenu par EFetch XML POST
  avec `NCBI_EMAIL` obligatoire et `NCBI_API_KEY` facultative. Une erreur
  globale EFetch arrête le run avant toute écriture de décisions ou de
  compteurs. Les secrets ne sont jamais journalisés.
- **Nom de fichier sûr.** Remplacer `/` par `_` dans les DOI pour les
  noms de fichiers (`10.1234_mock001.md`).
- **Chemin d'échec.** Parsing raté → `retrieval_failed` journalisé dans
  `decisions.jsonl`, jamais un trou silencieux.
- **Relances et compteurs.** Le journal reste append-only. Les compteurs du run
  ne comptent que les articles inclus dans ce run, jamais les fichiers anciens
  ou étrangers présents dans `sources/`.
- **Dernière entrée gagnante.** Pour une même identité, les consommateurs
  résolvent les événements `fulltext` valides dans l'ordre des lignes : la
  dernière entrée gagne, y compris lorsqu'il s'agit de `retrieval_failed`.

# Journalisation

Pour chaque article :
```json
{"ts":"...","doc":"10.xxx","stage":"fulltext","decision":"retrieved",
 "reason":"PDF parsé avec succès (OA)"}
```

En cas d'échec :
```json
{"ts":"...","doc":"10.xxx","stage":"fulltext","decision":"retrieval_failed",
 "reason":"PDF inaccessible (OA URL 404, pas de dropzone)"}
```

Mise à jour :
- `prisma.json` : `fulltext_assessed`, `fulltext_retrieved`,
  `fulltext_not_retrieved`
- `manifest.json` : `stage = "fulltext_done"`

# Pièges connus

- **Compatibilité des anciens journaux.** `screen_manual` est lu comme alias de
  `human_review`. Les anciens tuples `fulltext/include` et
  `fulltext/retrieved` restent extractibles ; `fulltext/needs_manual` reste un
  état bloquant. Les nouveaux événements utilisent uniquement le vocabulaire
  canonique. Tout tuple inconnu est signalé et compté dans
  `manifest.json` sous `journal_unknown_entries`.
- **Paywalls (403 Forbidden)** : de nombreux éditeurs (Elsevier, Springer, Wiley)
  bloquent le téléchargement automatisé. Les articles sans OA accessible
  passent en `retrieval_failed`. L'utilisateur peut déposer les PDF manuellement
  dans `inputs/pdfs/<doi_safe>.pdf`.
- **pymupdf4llm requis** : le parsing réel nécessite `pymupdf4llm`. Le venv
  recommandé est `~/.hermes/venvs/hermes-synthesis/`. Installation :
  ```bash
  uv venv ~/.hermes/venvs/hermes-synthesis
  uv pip install pymupdf4llm --python ~/.hermes/venvs/hermes-synthesis/bin/python
  ```
  Le script `fulltext.py` doit utiliser ce python, pas le python système.
- **PDF vides après parsing** : pymupdf4llm peut parser un PDF avec succès
  mais retourner < 500 caractères (slides, images scannées, ou PDF mal formé).
  Vérifier `len(content) > 500` avant de compter comme succès.

- **Articles fantômes — DOIs vides dans les décisions humaines.** Si le script
  annonce « Récupération pour N articles » alors que M étaient attendus
  (ex. N=6 au lieu de M=20), vérifier les DOIs des décisions humaines dans
  `decisions.jsonl`. Un DOI vide (`""`) empêche la correspondance avec
  `candidates.csv` (pas d'OA URL, pas de dropzone) → l'article est
  silencieusement ignoré. Remonter au skill `sysrev-review` pour corriger
  les DOIs (pitfall « DOIs fantômes après reconstruction »).
- **DOI vide — asymétrie volontaire des lecteurs.** Le lecteur de screening
  signale une entrée de décision sans `doc` puis l'ignore. Les consommateurs
  fulltext/extract ignorent silencieusement un `doc` vide : il ne peut être
  relié ni à `candidates.csv` ni à un fichier source. Cette structure ne doit
  pas être produite par le chemin canonique `review.py`.

# Critère de fin (Definition of Done)

- Chaque article inclus a un fichier Markdown dans `sources/`
- Les échecs sont journalisés (pas de trous silencieux)
- `prisma.json` reflète le nombre de fulltexts récupérés
- `manifest.json` indique `stage = "fulltext_done"`

# Étape suivante

Ce stage ne fait que RÉCUPÉRER les textes (accès). L'ÉLIGIBILITÉ sur le
texte intégral est tranchée par le stage suivant, `sysrev-screen-fulltext` :
un article récupéré peut encore être exclu s'il se révèle hors critères à la
lecture complète. Ne pas enchaîner directement sur `extract`.
