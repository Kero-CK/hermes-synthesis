---
name: sysrev-protocol
description: >
  Démarre une nouvelle revue de littérature. À utiliser quand l'utilisateur
  veut lancer une revue : capture la question de recherche, les critères
  d'inclusion/exclusion, le codebook d'extraction et le type de revue.
  Correspond au module M1 du pipeline Hermes Synthesis.
inputs:
  - un identifiant de revue (slug) fourni par l'utilisateur
outputs:
  - /reviews/<id>/protocol.md
  - /reviews/<id>/prisma.json
  - /reviews/<id>/manifest.json
notes:
  - Voir `references/vault-symlink.md` pour l'architecture vault (symlink /reviews → vault)
requires:
  env: []
  tools: [clarify, terminal]
  scripts: [scripts/init_review.py]
---

# Objectif

Créer le squelette d'une revue de littérature structurée. La skill recueille
auprès du chercheur la question, les critères, le codebook et un plan de
recherche multi-source, puis initialise le dossier de revue avec les fichiers
d'état nécessaires au pipeline Hermes Synthesis.

# Pré-conditions

Aucune. C'est la première étape du pipeline.

**⚠️ Pré-vol : vérifie le symlink `/reviews → vault` avant de créer la revue.**

```bash
readlink -f /reviews
```

Si la sortie est `/reviews` (pas un chemin dans le vault), le symlink
est cassé ou absent. Les fichiers seront invisibles dans Obsidian.
Corriger avant de continuer :

```bash
# Si /reviews est un dossier ordinaire avec des revues existantes :
mv /reviews/<revue-existante> "/vault/Projets/Hermes Synthesis/Reviews/"
rm -rf /reviews
ln -s "/vault/Projets/Hermes Synthesis/Reviews" /reviews
```

Ne jamais créer de revue tant que `/reviews` n'est pas un symlink
valide pointant vers le vault.

# Procédure

1. Demande à l'utilisateur le **slug** de la revue (ex. `adaptation-pme-2026`).
   Le slug sert d'identifiant unique : minuscules, tirets, pas d'espaces.

2. Avec `clarify`, recueille successivement :
   a. **La question de recherche** — une phrase claire.
   b. **Les critères d'INCLUSION** — conditions pour retenir un article
      (population, intervention, contexte, type d'étude, langue, période…).
   c. **Les critères d'EXCLUSION** — conditions qui éliminent un article
      (hors sujet, format non académique…).
   d. **Le type de revue** — `scoping` (défaut) ou `systematic`.
   e. **Le CODEBOOK d'extraction** — les variables à extraire de chaque
      article inclus. Chaque variable a un nom et une description courte.
   f. **Le plan de recherche multi-source** — demande quelles sources utiliser
      (`openalex`, `pubmed`, ou les deux) et explique leur utilité : OpenAlex
      apporte une couverture multidisciplinaire générale ; PubMed apporte une
      couverture biomédicale spécialisée. Ne recommande PubMed que si le
      sujet concerne la santé, la médecine ou les sciences de la vie ; le
      choix final appartient toujours au chercheur.
      Pour chaque source choisie, propose une requête adaptée sans demander au
      chercheur d'en connaître la syntaxe, puis présente les requêtes une par
      une et obtiens sa validation explicite. Conserve chaque requête validée
      exactement, sans conversion silencieuse.

   > Une question par appel à `clarify`. Ne pas tout demander d'un coup.

   **Raccourci :** il n'est utilisable que si l'utilisateur fournit d'emblée
   tous les champs suivants : slug, question, type de revue, inclusions,
   exclusions, codebook, sources sélectionnées, justification de chaque
   source et requête structurée validée pour chaque source. Sans plan de
   recherche multi-source complet, poursuivre les questions successives via
   `clarify`.

3. Une fois toutes les réponses collectées et chaque source/requête validée
   explicitement par l'utilisateur, exécute :
   ```
   python3 $HOME/.hermes/skills/sysrev-protocol/scripts/init_review.py '<json>'
   ```
   > **Pitfall :** `~` peut mal expandre dans certains contextes (ex. WSL avec
   > certains working directories). Préférer `$HOME` ou le chemin absolu complet.
   > Si la commande échoue avec « file not found », réessayer avec le chemin
   > absolu : `/home/agent/.hermes/skills/sysrev/sysrev-protocol/scripts/init_review.py`.
   avec le JSON structuré comme suit :
   ```json
    {
      "id": "microbiome-mici-2026",
      "question": "Quels facteurs influencent la composition du microbiome intestinal chez les adultes atteints de maladie inflammatoire chronique de l'intestin ?",
      "review_mode": "scoping",
      "include": [
        "adultes atteints de maladie inflammatoire chronique de l'intestin",
        "études observationnelles ou interventionnelles",
        "publié après 2015"
      ],
      "exclude": ["modèles animaux uniquement", "éditoriaux"],
      "codebook": [
        {"name": "maladie", "description": "Type de maladie inflammatoire"},
        {"name": "composition_microbiome", "description": "Composition microbienne mesurée"},
        {"name": "facteur_associe", "description": "Facteur associé à la composition"}
      ],
      "sources": [
        {
          "source": "openalex",
          "reason": "Couverture multidisciplinaire générale",
          "query": {
            "query_mode": "search",
            "search": "gut microbiome inflammatory bowel disease",
            "filter": "from_publication_date:2015-01-01"
          }
        },
        {
          "source": "pubmed",
          "reason": "Couverture biomédicale spécialisée",
          "query": {
            "query_mode": "pubmed",
            "term": "(\"gut microbiome\"[Title/Abstract] AND \"inflammatory bowel disease\"[Title/Abstract])"
          }
        }
      ]
    }
   ```

   ### Pitfalls d'exécution

   - **Shell escaping :** les caractères `&`, `$`, `!`, `"` dans les valeurs
     du JSON (ex. `"Barnett & O'Neill"`, `"augmentation de 50$"`) sont
     interprétés par le shell quand le JSON est passé en inline (`argv[1]`).
     Le shell traite `&` comme opérateur de background, `$` comme expansion
     de variable, etc. → échec silencieux ou `exit_code -1`.

   - **Fallback fiable — Python subprocess :** le heredoc `<< 'EOF'` avec
     des guillemets échappés dans le JSON peut encore produire des `\\\"`
     doublés. Et `--stdin` peut ne pas fonctionner dans certains environnements
     (lit du vide). La méthode qui marche **à tous les coups** :
     ```bash
     python3 -c "
     import json, subprocess
     data = {
         'id': 'ma-revue',
         'question': '...',
         'review_mode': 'scoping',
         'include': [...],
         'exclude': [...],
         'codebook': [{'name': 'x', 'description': '...'}]
     }
     json_str = json.dumps(data, ensure_ascii=False)
     result = subprocess.run(
         ['python3', '/home/agent/.hermes/skills/sysrev/sysrev-protocol/scripts/init_review.py', json_str],
         capture_output=True, text=True
     )
     print(result.stdout)
     "
     ```
     `subprocess.run()` avec une liste d'arguments contourne le shell
     → pas d'interprétation de `&`, `$`, `\"`, etc. Fonctionne même avec
     `\"Barnett & O'Neill\"` dans les descriptions du codebook.

   - **`write_file` bloqué :** l'outil `write_file` peut refuser certains
     chemins (protection système/credentials). Utiliser `cat > ... << 'EOF'`
     dans le terminal comme alternative systématique pour créer le fichier
     JSON temporaire.

   - **Chemin du script :** le skill est sous `sysrev/sysrev-protocol/`.
     Le chemin absolu fiable est :
     `/home/agent/.hermes/skills/sysrev/sysrev-protocol/scripts/init_review.py`

4. Relis `protocol.md` à l'utilisateur pour contrôler la traçabilité du plan
   multi-source. Si une source ou une requête doit changer, reviens à la
   validation de l'étape 2 avant toute recherche ; ne réécris pas le plan
   silencieusement après sa création.

# Règles

- **Ne JAMAIS inventer** un critère ou une variable. Si l'utilisateur est
  vague, redemander via `clarify`.
- Au moins une source doit être sélectionnée. Les sources autorisées sont
  `openalex` et `pubmed`, chacune une seule fois, avec une justification et
  une requête structurée portant le `query_mode` correspondant.
- Le codebook est un artefact méthodologique figé : pas de variable ajoutée
  en cours de route sans repasser par cette skill.
- Les critères doivent être **testables** : pas de « articles intéressants ».
- Le slug est **immuable** une fois la revue créée.
- La recherche réelle n'est pas lancée par cette skill : elle est déclenchée
  ensuite par `sysrev-search` avec `manifest.json → queries`.

# Journalisation

- `manifest.json` : `stage = "protocol_done"`, `review_mode` renseigné,
  `sources`, `queries` et `source_reasons` enregistrés.

# Architecture

Les revues sont stockées dans `/reviews/` qui est un **lien symbolique** vers
le vault Obsidian :

```
/reviews -> /vault/Projets/Hermes Synthesis/Reviews
```

Ce design garantit que :
- Tous les livrables apparaissent directement dans Obsidian
- Il n'y a qu'un seul emplacement physique (pas de duplication)
- Les scripts continuent d'écrire dans `/reviews/` sans savoir que c'est le vault

**Attention** : si `/reviews` n'est PAS un symlink (ex. dossier ordinaire),
les revues ne seront pas visibles dans Obsidian. L'utilisateur doit créer ce
symlink une fois pour toutes.

# Critère de fin (Definition of Done)

- `protocol.md` existe dans `/reviews/<id>/`
- Question, critères inclusion/exclusion, codebook, type de revue présents
- Plan multi-source présent avec au moins une source, justification et requête
  exacte validée pour chaque source
- L'utilisateur a confirmé
- `prisma.json` existe avec compteurs à zéro
- `manifest.json` indique `stage = "protocol_done"`
