---
name: sysrev-fulltext
description: >
  Récupère et parse les textes intégraux des articles inclus après screening.
  Télécharge les PDF open access, parse les PDF dropzone, convertit le tout
  en Markdown exploitable. Correspond au module M5 du pipeline Hermes Synthesis.
inputs:
  - /reviews/<id>/decisions.jsonl (décisions de screening finales)
  - /reviews/<id>/candidates.csv (pour les URLs OA et chemins dropzone)
  - /reviews/<id>/inputs/pdfs/ (dropzone)
  - /reviews/<id>/manifest.json (stage = "screen_done" ou "review_done")
outputs:
  - /reviews/<id>/sources/<doi_safe>.md (un fichier par article inclus)
  - prisma.json ("fulltext_assessed", "fulltext_not_retrieved") mis à jour
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
   - Cherche le PDF : URL open access d'abord, dropzone ensuite
   - Parse le PDF en Markdown (via `pymupdf4llm` en mode réel)
   - Écrit le résultat dans `sources/<doi_safe>.md`
   - Si le parsing échoue, marque `retrieval_failed`

4. Présente le résumé : combien récupérés, combien en échec.

# Règles

- **Ne jamais inventer de contenu.** Si le PDF est inaccessible, passer
  en `retrieval_failed` plutôt que de générer un faux texte.
- **Nom de fichier sûr.** Remplacer `/` par `_` dans les DOI pour les
  noms de fichiers (`10.1234_mock001.md`).
- **Chemin d'échec.** Parsing raté → `retrieval_failed` journalisé dans
  `decisions.jsonl`, jamais un trou silencieux.

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
- `prisma.json` : `fulltext_assessed`, `fulltext_not_retrieved`
- `manifest.json` : `stage = "fulltext_done"`

# Pièges connus

- **Compatibilité des anciens journaux.** `screen_manual` est lu comme alias de
  `human_review`. Les anciens tuples `fulltext/include` et
  `fulltext/needs_manual` restent reconnus comme `retrieved` et
  `retrieval_failed`, mais les nouveaux événements utilisent uniquement le
  vocabulaire canonique. Tout tuple inconnu est signalé et compté dans
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
