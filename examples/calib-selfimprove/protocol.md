# Protocole de revue — self-improving-agents

**Type de revue :** scoping
**Date de création :** 2026-07-02

## Question de recherche

Quels mécanismes permettent à un agent fondé sur un LLM d'améliorer son propre comportement pendant son utilisation (prompts, skills, mémoire), et comment sont-ils évalués ?

## Critères d'inclusion

- Agent ou système fondé sur un LLM
- Le système améliore son propre comportement pendant l'usage (inférence ou déploiement) via prompts, skills ou mémoire, sans ré-entraînement des poids
- Méthode évaluée ou étude empirique
- Publié entre 2022 et 2026, en anglais

## Critères d'exclusion

- Auto-amélioration en ML classique sans LLM (AutoML, NAS, méta-apprentissage pré-LLM, algorithmes évolutionnaires génériques)
- Auto-amélioration par ré-entraînement, mise à jour des poids, RL ou self-play (hors scope : amélioration pendant l'usage uniquement)
- Amélioration pilotée uniquement par un humain, sans boucle auto-référentielle
- Opinion, éditorial, ou article sans méthode ni évaluation

## Codebook d'extraction

- **mecanisme** : Type de mécanisme : self-refine, self-reward, acquisition de skills, mémoire, self-play, etc.
- **moment** : Quand l'amélioration a lieu : inférence ou déploiement
- **signal** : D'où vient le feedback : le modèle lui-même, l'environnement, un vérificateur, ou un humain
- **evaluation** : Comment l'amélioration est mesurée : benchmark, tâche, métrique
- **limites** : Risques signalés : dégénérescence, reward hacking, dérive, etc.
