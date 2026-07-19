---
name: sysrev-report
description: >
  Génère le rapport final d'une revue de littérature : synthèse des résultats,
  diagramme de flux PRISMA, export bibliographique RIS, et rapport Markdown
  complet. Correspond au module M7 du pipeline Hermes Synthesis.
inputs:
  - /reviews/<id>/protocol.md (question, méthode)
  - /reviews/<id>/prisma.json (compteurs du flux)
  - /reviews/<id>/extraction.csv (données extraites)
  - /reviews/<id>/decisions.jsonl (journal d'audit)
  - /reviews/<id>/manifest.json (stage = "extract_done")
outputs:
  - /reviews/<id>/report.md (rapport de synthèse)
  - /reviews/<id>/prisma.md (diagramme de flux)
  - /reviews/<id>/export.ris (export bibliographique)
  - manifest.json mis à jour (stage = "report_done")
requires:
  env: [LLM_SYNTHESIS]
  tools: [terminal]
  scripts: [scripts/report.py]
---

# Objectif

Produire le livrable final de la revue : un rapport de synthèse lisible,
le diagramme de flux PRISMA, et un export bibliographique compatible
Zotero/Mendeley. Le rapport est structuré pour être quasi publiable
(PRISMA-ScR ou PRISMA 2020 selon le type de revue).

# Pré-conditions

- `manifest.json` indique `stage = "extract_done"`
- `extraction.csv` existe avec des données
- `prisma.json` a tous les compteurs remplis
- `protocol.md` existe
- le codebook d'extraction est présent et non vide
- le nombre de cellules dans `extraction.csv` correspond à textes récupérés × variables

# Procédure

1. Exécute le script de rapport :
   ```
   python3 ~/.hermes/skills/sysrev/sysrev-report/scripts/report.py '<json>'
   ```
   avec :
   ```json
   {
     "id": "ma-revue",
     "mock": true
   }
   ```

2. Le script :
   - Lit `protocol.md` pour le contexte (question, type de revue)
   - Lit `prisma.json` pour les compteurs
   - Lit `extraction.csv` pour les résultats
   - Génère `report.md` : synthèse narrative structurée
   - Génère `prisma.md` : diagramme de flux Mermaid
   - Génère `export.ris` : export bibliographique
   - Met à jour `manifest.json`

   Si le codebook manque ou si le nombre de cellules est incohérent, le rapport
   est refusé avant toute synthèse LLM et ne passe jamais à `report_done`.

3. Présente le rapport à l'utilisateur.

# Règles

- **Reporting conforme.** Scoping review → flux PRISMA-ScR.
  Systematic review → PRISMA 2020.
- **Divulgation IA.** Le rapport mentionne les modèles utilisés,
  leurs versions, et le rôle de l'IA vs l'humain (PRISMA-trAIce).
- **Pas d'invention.** Les résultats sont issus de `extraction.csv`.
  Ne pas ajouter de conclusion non étayée par les données.
- **Compteurs distincts.** Le rapport sépare les articles des cellules : textes
  récupérés, articles soumis, articles avec/sans donnée exploitable, cellules
  tentées, valeurs exploitables, `NON TROUVÉ`, erreurs API et citations rejetées.
- **Contexte LLM.** Le prompt utilise `documents` pour les articles et `cells`
  pour les variables ; un nombre de cellules ne doit jamais être présenté comme
  un nombre d'articles.
- **Symlink vault.** `/reviews` est un symlink vers le vault Obsidian.
  Les livrables sont automatiquement dans le vault. Ne pas copier
  manuellement — le script signale juste `(via symlink)`.

# Pièges connus

- **Indentation de `generate_report()`** : vérifier que `lines = [` est
  bien fermé avec `]` avant tout `lines.extend(...)`. Le script original
  avait un `lines.extend` imbriqué à l'intérieur de la liste (jamais fermée).
- **Vérification syntaxe après patch** : toujours lancer
  `python3 -c "import py_compile; py_compile.compile(...)"` après modification.
- **Symlink /reviews → vault** : si `/reviews` est un lien symbolique vers le
  vault, toute tentative de `shutil.copy2` entre ces deux chemins échoue avec
  `SameFileError`. Le bloc de copie vault dans `report.py` a été supprimé pour
  cette raison — les livrables sont déjà dans le vault via le symlink.
  Si tu restaures ce bloc, vérifie d'abord que `/reviews` n'est pas un symlink.

# Fichiers produits

### report.md
```markdown
# Revue : [titre]
**Type :** scoping review
**Date :** 2026-06-25

## Résumé
...

## Méthode
- Question, critères, sources, dates

## Résultats
- Flux PRISMA
- Synthèse par variable

## Discussion
...

## Déclaration IA
Modèles utilisés : ...
```

### prisma.md
Diagramme Mermaid du flux PRISMA (identifiés → dédup → screenés → fulltext → inclus).

### export.ris
Format RIS importable dans Zotero/Mendeley pour les articles inclus.

# Journalisation

- `manifest.json` : `stage = "report_done"`, `report_date`

# Pièges connus

- **Indentation dans `generate_report()`** : la construction de la liste `lines = [`
  et les appels `lines.extend()` doivent être au même niveau d'indentation. Si un
  `lines.extend()` est indenté à l'intérieur de `lines = [`, la liste n'est jamais
  fermée → `SyntaxError: '[' was never closed`. Vérifier que chaque `]` de fermeture
  est au bon niveau.

- **Conflit symlink `/reviews → vault`** : si `/reviews` est un lien symbolique vers
  le vault, le bloc de copie des livrables dans `main()` cause un `SameFileError`
  (il tente de copier un fichier sur lui-même). Supprimer ce bloc ou ajouter un
  check `os.path.samefile()`.

# Critère de fin (Definition of Done)

- `report.md` existe, structuré, avec tous les résultats
- `prisma.md` affiche le diagramme de flux correct
- `export.ris` contient les articles inclus
- `manifest.json` indique `stage = "report_done"`
