---
name: review
description: >
  Lance une revue de littérature complète en une seule commande.
  Demande la question, les critères et le codebook, puis exécute
  automatiquement tout le pipeline : protocol → search → dedup →
  screen → review (HITL) → fulltext → extract → report.
  Le chercheur n'a qu'à répondre aux questions et trancher les
  cas ambigus.
inputs:
  - une question de recherche fournie par l'utilisateur
outputs:
  - /reviews/<id>/ (dossier complet)
  - /vault/Projets/Hermes Synthesis/reviews/<id>/ (livrables)
requires:
  env: []
  tools: [clarify, terminal]
  scripts: []
---

# Objectif

Simplifier l'expérience utilisateur au maximum : une seule commande
pour toute la revue. Le chercheur pose sa question, définit ses critères,
et le pipeline s'exécute automatiquement — en s'arrêtant uniquement
pour les validations humaines (protocole, requêtes, cas ambigus).

# Pré-conditions

1. **Vérifier le symlink `/reviews` → vault.** Sans ce symlink, les revues
   sont créées dans un dossier ordinaire invisible à Obsidian. Vérifier :
   ```bash
   readlink -f /reviews
   ```
   Si le résultat est `/reviews` (et non un chemin dans `/vault/`), le symlink
   est cassé ou inexistant. Le réparer :
   ```bash
   # Sauvegarder les revues existantes si besoin
   mv /reviews/* "/vault/Projets/Hermes Synthesis/Reviews/" 2>/dev/null
   rm -rf /reviews
   ln -s "/vault/Projets/Hermes Synthesis/Reviews" /reviews
   ```
   Voir `references/vault-symlink.md` dans `sysrev-protocol` pour le détail.

# Procédure

## Phase 1 — Protocole
1. Demander le **slug** de la revue.
2. Recueillir la **question de recherche**.
3. Recueillir les **critères inclusion/exclusion**.
4. Recueillir le **type de revue** (scoping/systematic).
5. Recueillir le **codebook** d'extraction.
6. Avant d'exécuter `sysrev-protocol`, recueillir le choix des sources et la
   justification de chaque source. Pour chaque source sélectionnée, proposer
   une requête adaptée, la présenter séparément et obtenir sa validation
   humaine explicite. Conserver une question par appel `clarify`, puis
   demander une confirmation explicite du plan final avant d'exécuter la skill
   `sysrev-protocol`.

## Phase 2 — Recherche
7. Relire `/reviews/<id>/manifest.json` après le protocole et charger
   `sources`, `source_reasons` et `queries`. Le protocole est l'autorité pour
   le choix des sources et les requêtes validées.
8. Présenter une dernière fois à l'utilisateur les sources, leurs
   justifications et les requêtes exactes enregistrées dans `queries`.
9. Transmettre `manifest.json → queries` tel quel à `sysrev-search` en mode
   réel (pas de mock). Ne pas régénérer, reformuler, convertir ou compléter
   silencieusement une requête après le protocole.
9a. Si une source ou une requête doit changer, arrêter la recherche et revenir
    à `sysrev-protocol` pour une nouvelle validation humaine avant toute
    exécution. Relire ensuite le nouveau `manifest.json`.
9b. Relire `/reviews/<id>/manifest.json` et vérifier que
     `search_status` vaut exactement `"complete"`. Si le champ est absent,
     inconnu, `incomplete`, `capped` ou `error`, arrêter le pipeline avant
     `sysrev-dedup` et `sysrev-screen`. Pour `capped`, corriger la recherche
    ou augmenter `HARD_LIMIT` puis la relancer. Aucun `force` de screening ne
    permet de contourner cette barrière.

## Phase 3 — Déduplication
10. Exécuter la skill `sysrev-dedup`.
11. Annoncer le nombre d'articles après déduplication.

## Phase 4 — Screening
12. Exécuter la skill `sysrev-screen` en mode réel (LLM).
13. Annoncer : X inclus, Y exclus, Z ambigus.

## Phase 5 — HITL (si cas ambigus)
14. Si `to_review.jsonl` n'est pas vide :
    - Exécuter la skill `sysrev-review`.
    - Pour les listes ≤15 cas : présenter la liste complète, une décision
      par ligne.
    - Pour les listes >15 cas : **regrouper par pertinence** (🎯 Très probables,
      🟡 Potentiels, 🔴 Probablement hors sujet) pour permettre des décisions
      groupées (« include tout A+B, exclude C »).
    - Le chercheur répond en batch, pas un cas à la fois.

## Phase 6 — Textes intégraux
15. Exécuter la skill `sysrev-fulltext`.
16. Annoncer : X récupérés, Y échecs.

## Phase 7 — Extraction
17. Exécuter la skill `sysrev-extract` en mode réel (LLM).
18. Annoncer : X cellules extraites, Y NON TROUVÉ.

## Phase 8 — Rapport
19. Exécuter la skill `sysrev-report`.
20. Annoncer : rapport prêt, disponible dans le vault.

# Règles

- **Ne jamais sauter le HITL.** Si `to_review.jsonl` contient des cas
  après le screening, TOUJOURS les présenter à l'humain avant de
  continuer.
- **Transparence.** Annoncer chaque étape avant de l'exécuter.
- **Pauses acceptées.** L'utilisateur peut interrompre à tout moment
  et reprendre avec `sysrev-resume`.
- **Comparaison Narrow vs Broad.** Pour isoler l'effet du vocabulaire de
  maladaptation, lancer deux runs identiques ne différant que par le bloc 1.
  Voir `references/delta-narrow-vs-broad.md`.

# Pièges connus

- **Caractères spéciaux dans les arguments shell.** Les JSON contenant
  `&`, `"` ou `'` cassent quand ils sont passés en argument shell direct
  (`python3 script.py '<json>'`). Solution fiable : écrire le JSON avec
  Python (`json.dump`), puis le passer via `subprocess.run()` avec le
  JSON comme `argv[1]` — jamais via le shell.
- **Mode `--stdin` instable.** Le flag `--stdin` de certains scripts
  (notamment `search.py`) peut retourner `Erreur JSON : Expecting value`
  même avec un fichier valide. Contournement : utiliser `subprocess.run()`
  avec le JSON en `argv[1]`.
- **Extraction = opération longue.** La phase d'extraction (10+ articles
  × 9 variables × double passe LLM) dépasse souvent les 600s du foreground.
  Lancer en `background=true` avec `notify_on_complete=true`.

# Critère de fin

`manifest.json` indique `stage = "report_done"`.
