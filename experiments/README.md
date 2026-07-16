# Experiments — la carte

Ce dossier contient l'histoire complète du moteur de screening par critères,
menée du 15 au 16 juillet 2026. **Résultat final : moteur clos, allowlist
vide — la machine pré-remplit les grilles d'évaluation avec citations, un
humain prend chaque décision.** Détail : `ERRATUM-MODEL-IDENTITY.md` (tous
les runs ont été servis par deepseek-v4-flash) et le document de clôture
signé (voir tableau).

## Comment lire un dossier d'expérience

Chaque dossier = un chapitre, toujours organisé pareil :

| Fichier | Question à laquelle il répond |
|---|---|
| `CHARTER.md` | Qu'a-t-on décidé de tester, avant de voir quoi que ce soit ? |
| `PREREGISTRATION*.md` | Les critères de réussite/échec exacts, gelés avant le run |
| `prompt.txt`, `criteria.json`, `run_*.py` | Le matériel testé, figé |
| `DEVIATIONS*.md` | Ce qui a dévié pendant l'implémentation, assumé |
| `results/<timestamp>/` | Les preuves : réponses brutes, assessments, rapport |
| `*checklist*.md` | Les vérifications humaines de Cedric, item par item |

## L'histoire, dans l'ordre

| Chapitre | Dossier | Verdict |
|---|---|---|
| v0 — premier prompt | `hometest-criteria-matrix-v0/` | Falsifié (citations paraphrasées, oracles défectueux) |
| v1 — citations par phrase + glossaire | `hometest-criteria-matrix-v1/` | **Validé** (reasoner) ; chat éliminé |
| Calibration v1 — 40 articles | `hometest-criteria-matrix-v1-calibration/` | Allowlist {I1} scellée ; E1/E5/E4/I4 recalés |
| v2 — discipline not_met/not_reported | `hometest-criteria-matrix-v2/` | Falsifié (l'erreur s'est déplacée) ; découverte du non-déterminisme |
| v3 — étiquetage des sources | `hometest-criteria-matrix-v3/` | Falsifié (sécurité tenue, invalides trop nombreux) |
| Erratum modèles | `ERRATUM-MODEL-IDENTITY.md` | Alias ≠ modèle servi ; v4-pro jamais testé (parqué) |
| Calibration terminale + clôture | `hometest-criteria-matrix-final-calibration/` | **Allowlist finale : vide** ; clôture signée (`ALLOWLIST-CLOSURE.md` dans le run) |

## Ce que ça a établi

- **Sûreté** : sur l'ensemble des runs, aucun article à garder n'a jamais
  été auto-exclu, aucun article à exclure n'a jamais été auto-inclus.
- **Auditabilité** : chaque assessment porte des citations exactes,
  vérifiées mécaniquement contre le texte source.
- **Lucidité** : le non-déterminisme de l'API à température 0 est mesuré
  (≈50–73 % de stabilité inter-réplicats) et neutralisé par l'exigence de
  reproduction.
- **Limite honnête** : sous ces contraintes, l'exclusion automatique n'a
  pas survécu à la mesure (0 % d'automatisation). La valeur du moteur est
  le pré-assessment audité, pas la décision autonome.

Le moteur ne sera rouvert que sur besoin documenté constaté en production.
Chantiers suivants : sources multiples, puis UX chercheur.
