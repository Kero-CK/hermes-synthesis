# Hermes Synthesis — plan directeur de la recherche multi-source

Statut : décision d'architecture validée le 17 juillet 2026.

Ce document est le point de référence pour ajouter des sources de recherche
sans complexifier inutilement le moteur.

## Décisions acquises

- OpenAlex reste le socle généraliste.
- Les nouvelles sources sont intégrées directement par leur API officielle.
- `paper-search-mcp` n'est pas une dépendance de production.
- Une seule source est ajoutée et validée à la fois.
- Une source disciplinaire est choisie explicitement dans le protocole.
- Une invocation interroge une seule source avec sa requête exacte.
- La déduplication reste exclusivement la responsabilité de `sysrev-dedup`.
- Une erreur, une réponse partielle ou une limite atteinte n'est jamais
  transformée silencieusement en recherche complète.
- Zéro résultat peut être un résultat valide : le statut reste `complete`,
  avec un compteur à zéro et une raison explicite.
- Unpaywall sert à résoudre légalement un DOI vers une copie ouverte. Il ne
  compte pas comme source d'identification dans PRISMA.
- Semantic Scholar est réservé en priorité au snowballing par citations, dans
  un bloc ultérieur.
- Sci-Hub reste désactivé et hors du produit.

## Flux cible

```text
Protocole
  → choix et justification des sources
  → requête adaptée à chaque source
  → recherche source par source
  → normalisation avec provenance
  → candidates.csv
  → déduplication
  → screening et suite de la revue
```

Le protocole conserve pour chaque source :

- son nom ;
- la raison de son inclusion ;
- la requête exacte ;
- les filtres et limites ;
- la date de recherche ;
- la version ou l'endpoint de l'API.

## Rôle des différentes briques

| Brique | Rôle | Position actuelle |
|---|---|---|
| OpenAlex | Recherche généraliste multidisciplinaire | En production |
| Base disciplinaire | Couverture spécialisée choisie dans le protocole | À ajouter source par source |
| CORE ou OpenAIRE | Dépôts ouverts et productions hors revues classiques | Un seul à retenir après microtest |
| Unpaywall | Résolution OA à partir d'un DOI | Après identification et déduplication |
| Dropzone PDF | Documents obtenus légalement par l'utilisateur | Déjà disponible |
| Semantic Scholar | Citations, références et articles similaires | Snowballing V2 |
| Crossref | Vérification DOI et complément de métadonnées | Pas une source de recherche prioritaire |

## Contrat minimal d'un connecteur

Chaque connecteur doit :

1. recevoir une requête déjà validée pour sa source ;
2. utiliser uniquement l'API officielle ;
3. gérer pagination, limites, timeouts et reprise contrôlée ;
4. retourner les articles dans le format commun :
   `title`, `doi`, `year`, `abstract`, `oa_url` ;
5. préserver la provenance :
   `source`, `query`, `date`, endpoint et version ;
6. rapporter le nombre récupéré et, si l'API le fournit, le nombre attendu ;
7. déclarer honnêtement `complete`, `incomplete`, `capped` ou `error` ;
8. ne jamais dédupliquer les résultats d'une autre source ;
9. ne jamais inventer une métadonnée absente.

Si une API ne fournit pas de compteur total, le connecteur doit déclarer le
compteur attendu comme inconnu, jamais comme zéro.

## Checklist obligatoire pour chaque source

### 1. Décision méthodologique

- [ ] Décrire ce que cette source apporte par rapport à OpenAlex.
- [ ] Identifier les disciplines et types de documents couverts.
- [ ] Vérifier qu'elle possède une API officielle exploitable.
- [ ] Documenter ses conditions d'utilisation et ses limites.
- [ ] Décider si elle sert à l'identification, à l'enrichissement ou au
      téléchargement.
- [ ] Justifier son ajout dans le protocole produit.

### 2. Contrat et accès

- [ ] Documenter la syntaxe de recherche officielle.
- [ ] Définir la traduction depuis le protocole.
- [ ] Identifier la clé, l'e-mail ou l'autorisation éventuellement nécessaire.
- [ ] Épingler l'endpoint et la version d'API.
- [ ] Définir pagination, plafond, timeout et politique de retry.
- [ ] Définir le mapping exact des champs vers le format Hermes.

### 3. Implémentation isolée

- [ ] Ajouter uniquement le connecteur concerné.
- [ ] Ne pas modifier les décisions des étapes suivantes du moteur.
- [ ] Conserver la signature commune des fonctions de recherche.
- [ ] Enregistrer requête, source, date, compteurs et statut.
- [ ] Ne pas ajouter de fallback silencieux vers une autre source.

### 4. Tests techniques

- [ ] Requête connue retournant des résultats.
- [ ] Requête valide retournant zéro résultat.
- [ ] Clé absente ou invalide.
- [ ] Erreur HTTP et timeout simulés.
- [ ] Pagination sur plusieurs pages.
- [ ] Limite volontaire atteinte (`capped`).
- [ ] Métadonnées manquantes.
- [ ] DOI et caractères Unicode correctement normalisés.

### 5. Validation dans Hermes

- [ ] Les lignes produites respectent le schéma de `candidates.csv`.
- [ ] La provenance est complète sur chaque ligne.
- [ ] `manifest.json` porte le statut réel.
- [ ] Un run incomplet ne peut pas passer pour complet.
- [ ] La déduplication fusionne correctement les recouvrements avec OpenAlex.
- [ ] Les étapes suivantes refusent un corpus `error` ou `incomplete`.
- [ ] Les résultats et limites observés sont documentés.

### 6. Onboarding utilisateur

- [ ] Expliquer simplement à quoi sert la source.
- [ ] Indiquer si l'accès est obligatoire, recommandé ou facultatif.
- [ ] Donner l'URL officielle pour obtenir l'accès.
- [ ] Tester l'accès lors de la configuration.
- [ ] Ne jamais afficher de secret après son enregistrement.
- [ ] Permettre de ne pas sélectionner la source.
- [ ] Écrire le choix et sa justification dans le protocole.

## Ordre de construction

### Bloc 0 — Fondation multi-source

- [x] Figer des tests de non-régression pour OpenAlex.
- [x] Formaliser le contrat commun des connecteurs.
- [x] Vérifier la syntaxe booléenne OpenAlex officiellement recommandée.
- [x] Définir les fixtures et preuves conservées pour chaque test de source.
- [x] Faire valider le contrat avant d'ajouter une API.

**Fondation de sécurité du Bloc 0 validée.** OpenAlex est désormais cadré
pour le mode structuré recommandé ; PubMed reste la prochaine source.

### Décision finale OpenAlex (2026-07-19)

- Hermes utilise exclusivement l'objet structuré OpenAlex avec
  `query_mode = "search"`, `search` obligatoire et `filter` séparé facultatif.
- Toute chaîne ou ancien format OpenAlex est refusé avant réseau et écriture ;
  aucune conversion automatique n'est autorisée.
- Les dossiers actuellement présents sont des tests ; aucune revue utilisateur
  historique ne doit être préservée ou migrée.
- Le `query_mode = "search"` et la requête exacte restent enregistrés dans
  `manifest.json`.
- La comparaison temporaire des deux modes est clôturée et son outil de test
  est supprimé ; aucune activation expérimentale ne reste ouverte.

### Lot 0E — OpenAlex `search=` (validé 2026-07-19)

- [x] Adopter la méthode OpenAlex officiellement recommandée avec `search=`.
- [x] Maintenir séparément les filtres de date et les autres filtres structurés
      dans `filter=`.
- [x] Refuser les chaînes OpenAlex et interdire toute conversion silencieuse.
- [x] Conserver le `query_mode` de chaque recherche dans `manifest.json`.
- [x] Vérifier pagination, statuts, compteurs, DOI/source_id et `HARD_LIMIT`.
- [x] Valider le chemin structuré avec des tests sans réseau.
- [x] Supprimer l'outil temporaire de comparaison après validation.

### Bloc 1 — Premier connecteur disciplinaire

Prochaine action : **PubMed**, car sa recherche MeSH et sa structure diffèrent
réellement d'OpenAlex.

- [ ] Confirmer PubMed comme premier connecteur.
- [ ] Implémenter le connecteur.
- [ ] Exécuter toute la checklist d'une source.
- [ ] Valider avant de passer au bloc 2.

### Bloc 2 — Deuxième famille disciplinaire

Recommandation actuelle : **arXiv**, pour les prépublications en informatique,
mathématiques et sciences physiques.

- [ ] Réévaluer son gain réel par rapport à OpenAlex.
- [ ] Implémenter seulement si le gain est démontré.
- [ ] Exécuter toute la checklist d'une source.

### Bloc 3 — Troisième famille disciplinaire

Recommandation actuelle : **ERIC**, pour l'éducation et une partie des sciences
sociales.

- [ ] Vérifier les conditions et possibilités de l'API.
- [ ] Implémenter seulement si l'accès est suffisamment stable.
- [ ] Exécuter toute la checklist d'une source.

### Bloc 4 — Dépôts ouverts

- [ ] Faire un microtest comparatif CORE / OpenAIRE.
- [ ] Mesurer couverture utile, qualité des métadonnées et stabilité.
- [ ] N'en retenir qu'un pour la première version.
- [ ] Exécuter toute la checklist d'une source.

### Bloc 5 — Résolution du texte intégral

- [ ] Brancher Unpaywall après identification et déduplication.
- [ ] Ne jamais compter Unpaywall comme base PRISMA.
- [ ] Conserver la provenance de l'URL OA trouvée.
- [ ] Garder la dropzone comme solution pour les accès institutionnels.

### Bloc 6 — Snowballing

- [ ] Tester Semantic Scholar sur les citations et références.
- [ ] Séparer les articles trouvés par snowballing des résultats initiaux.
- [ ] Reporter cette provenance séparément dans PRISMA.

## Définition de « bloc validé »

Un bloc est terminé seulement si :

- son intérêt méthodologique est démontré ;
- ses tests passent ;
- ses erreurs sont visibles ;
- sa provenance est complète ;
- sa documentation utilisateur existe ;
- la cohérence globale est vérifiée ;
- le passage au bloc suivant est explicitement documenté.

## Décisions encore ouvertes

Ces décisions seront prises au début du bloc concerné, pas avant :

- PubMed est-il bien le premier connecteur ?
- CORE ou OpenAIRE pour les dépôts ouverts ?
- Quand ajouter arXiv et ERIC selon les besoins réels des utilisateurs ?
- Quel stockage sécurisé employer pour les clés dans la future interface ?
- Quand le snowballing devient-il prioritaire ?

## Prochaine action

Commencer le cadrage officiel du connecteur **PubMed**. Aucun changement de
syntaxe ou de comportement OpenAlex n'est requis pour ce passage.
