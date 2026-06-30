---
name: sysrev-fulltext
description: >
  Récupère et parse les textes intégraux des articles inclus après screening.
  Télécharge les PDF open access, parse les PDF dropzone, convertit le tout
  en Markdown exploitable. Correspond au module M5 du pipeline Hermes Synthesis.
inputs:
  - /reviews/<id>/decisions.jsonl (articles avec decision=include)
  - /reviews/<id>/candidates.csv (pour les URLs OA et chemins dropzone)
  - /reviews/<id>/inputs/pdfs/ (dropzone)
  - /reviews/<id>/manifest.json (stage = "screen_done" ou "review_done")
outputs:
  - /reviews/<id>/sources/<doi_safe>.md (un fichier par article inclus)
  - prisma.json ("fulltext_assessed", "excluded_fulltext") mis à jour
  - manifest.json mis à jour
requires:
  env: []
  tools: [terminal]
  scripts: [scripts/fulltext.py]
---

# Objectif

Récupérer le texte intégral de chaque article inclus lors du screening.
Deux sources : URL open access (téléchargement automatique) et dropzone
(PDF fournis par l'utilisateur). Convertir en Markdown pour les étapes
suivantes (extraction notamment).

# Pré-conditions

- `manifest.json` indique `stage = "screen_done"` ou `"review_done"`
- `decisions.jsonl` contient des décisions `include` (tous stages : auto `screen_title_abstract` ET humain `human_review`)
- `candidates.csv` contient les URLs OA et les chemins dropzone

# Procédure

1. Identifie les articles à traiter : ceux avec `decision = "include"`
   dans `decisions.jsonl`.

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
   - Cherche le PDF : URL open access d'abord, dropzone ensuite
   - Parse le PDF en Markdown (via `pymupdf4llm` en mode réel)
   - Écrit le résultat dans `sources/<doi_safe>.md`
   - Si le parsing échoue, marque `needs_manual`

4. Présente le résumé : combien récupérés, combien en échec.

# Règles

- **Ne jamais inventer de contenu.** Si le PDF est inaccessible, passer
  en `needs_manual` plutôt que de générer un faux texte.
- **Nom de fichier sûr.** Remplacer `/` par `_` dans les DOI pour les
  noms de fichiers (`10.1234_mock001.md`).
- **Chemin d'échec.** Parsing raté → `needs_manual` journalisé dans
  `decisions.jsonl`, jamais un trou silencieux.

# Journalisation

Pour chaque article :
```json
{"ts":"...","doc":"10.xxx","stage":"fulltext","decision":"include",
 "reason":"PDF parsé avec succès (OA)"}
```

En cas d'échec :
```json
{"ts":"...","doc":"10.xxx","stage":"fulltext","decision":"needs_manual",
 "reason":"PDF inaccessible (OA URL 404, pas de dropzone)"}
```

Mise à jour :
- `prisma.json` : `fulltext_assessed`, `excluded_fulltext`
- `manifest.json` : `stage = "fulltext_done"`

# Pièges connus

- **Stage filter trop restrictif (corrigé)** : l'ancienne version du script
  filtrait uniquement `stage == "screen_title_abstract"`, ce qui ignorait
  les articles inclus par décision humaine (`stage == "human_review"`).
  Le script accepte maintenant TOUS les articles avec `decision == "include"`,
  quel que soit leur stage.
- **Paywalls (403 Forbidden)** : de nombreux éditeurs (Elsevier, Springer, Wiley)
  bloquent le téléchargement automatisé. Les articles sans OA accessible
  passent en `needs_manual`. L'utilisateur peut déposer les PDF manuellement
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

# Critère de fin (Definition of Done)

- Chaque article inclus a un fichier Markdown dans `sources/`
- Les échecs sont journalisés (pas de trous silencieux)
- `prisma.json` reflète le nombre de fulltexts récupérés
- `manifest.json` indique `stage = "fulltext_done"`
